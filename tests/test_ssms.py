"""Έλεγχοι πραγματικού SSMS UI, συσχέτισης αιτημάτων και CLI."""

import argparse
import asyncio
import csv
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))
from app.sql_workspace import SqlFiles, SqlResultData
from app.sql_cli import SqlCLI


def sample_result(request_id='TEST', client_code='TEST', **fields):
    """Παρέχει συνθετικά δεδομένα με διπλές επικεφαλίδες και ελληνικά."""
    return {'type': 'sql_result', 'request_id': request_id, 'client_code': client_code,
            'bo_connection_id': 1, 'success': True, 'driver': 'TEST', 'elapsed_ms': 25,
            'batches': [{'batch_index': 1, 'result_sets': [
                {'columns': ['Name', 'Name', 'Value'], 'rows': [['Αθήνα', 'comma,value', None], ['Β', 'tab\tvalue', 'line\nvalue']], 'limited': True}]}], **fields}


class SqlDataTests(unittest.TestCase):
    """Ελέγχει αρχεία και εξαγωγή χωρίς παραγωγικό SQL Server."""

    def test_sql_file_encodings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.sql'
            text = "SELECT N'Αθήνα';"
            for encoding in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1253'):
                with self.subTest(encoding=encoding):
                    path.write_bytes(text.encode(encoding))
                    self.assertEqual(SqlFiles.read(path)[0], text)

    def test_delimited_roundtrip_handles_special_cells(self):
        item = SqlResultData.sets(sample_result())[0]
        self.assertTrue(item['limited'])
        for delimiter in ('\t', ','):
            text = SqlResultData.delimited(item['columns'], item['rows'], delimiter)
            rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
            self.assertEqual(rows[0], ['Name', 'Name', 'Value'])
            self.assertEqual(rows[1], ['Αθήνα', 'comma,value', 'NULL'])
            self.assertEqual(rows[2], ['Β', 'tab\tvalue', 'line\nvalue'])

    def test_batch_failure_is_reported_even_when_outer_success_true(self):
        payload = sample_result(batches=[{'batch_index': 1, 'error': 'Test batch failure', 'rowcount': -1}])
        self.assertTrue(SqlResultData.failed(payload))
        self.assertIn('Test batch failure', SqlResultData.messages(payload))

    def test_cli_payload_and_formats(self):
        args = SqlCLI.parser().parse_args(['--client', 'TEST', '--query', 'SELECT 1', '--format', 'csv'])
        payload = SqlCLI.payload(args)
        self.assertEqual(payload['type'], 'sql_execute')
        self.assertEqual(payload['sql_text'], 'SELECT 1')
        text = SqlCLI.render(sample_result(), args)
        self.assertTrue(text.startswith('\ufeff'))
        args.result_set = 2
        with self.assertRaises(ValueError):SqlCLI.render(sample_result(), args)
        args.timeout = 0
        with self.assertRaises(ValueError):SqlCLI.payload(args)

    def test_cli_protocol_and_cancel_stay_on_same_socket(self):
        import websockets
        async def scenario(cancel=False):
            """Ελέγχει το πραγματικό πρωτόκολλο μέσω προσωρινού τοπικού server."""
            ready = asyncio.Event()
            cancelled = asyncio.Event()
            async def handler(ws):
                self.assertEqual(json.loads(await ws.recv())['type'], 'authenticate')
                await ws.send(json.dumps({'type': 'clients_update'}))
                await ws.send(json.dumps({'type': 'dashboard_connected'}))
                payload = json.loads(await ws.recv())
                ready.set()
                if cancel:
                    message = json.loads(await ws.recv())
                    self.assertEqual(message['type'], 'sql_cancel')
                    self.assertEqual(message['request_id'], payload['request_id'])
                    cancelled.set()
                else:
                    await ws.send(json.dumps(sample_result('OLD')))
                    await ws.send(json.dumps(sample_result(payload['request_id'])))
            async with websockets.serve(handler, '127.0.0.1', 0) as server:
                config = SimpleNamespace(dashboard_token='FAKE', dashboard_websocket_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
                args = SqlCLI.parser().parse_args(['--client', 'TEST', '--query', 'SELECT 1'])
                task = asyncio.create_task(SqlCLI().request(config, SqlCLI.payload(args)))
                await asyncio.wait_for(ready.wait(), 3)
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):await task
                    await asyncio.wait_for(cancelled.wait(), 3)
                else:
                    self.assertTrue((await task)['success'])
        asyncio.run(scenario())
        asyncio.run(scenario(True))


@unittest.skipUnless(importlib.util.find_spec('customtkinter') and
                     (os.name == 'nt' or os.environ.get('DISPLAY')), 'Απαιτεί CustomTkinter και οθόνη.')
class SqlUITests(unittest.TestCase):
    """Δοκιμάζει πραγματικά widgets και αποκλείει δεύτερη εκτέλεση μέχρι τελικό αποτέλεσμα."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.sql_tab import SqlTab
        self.root = ctk.CTk(); self.root.geometry('1350x900')
        self.root.grid_columnconfigure(0, weight=1);self.root.grid_rowconfigure(0, weight=1)
        self.sent = []
        self.tab = SqlTab(self.root, 'TEST', self.sent.append)
        self.tab.grid(sticky='nsew')
        self.tab.set_bo_values(['ID 1 - InitialTest', 'ID 2 - OtherTest'], 'ID 1 - InitialTest')
        self.root.update();self.tab._apply_layout();self.root.update()

    def tearDown(self):
        self.tab.destroy()
        for job in self.root.tk.call('after', 'info'):self.root.after_cancel(job)
        self.root.destroy()

    def reply(self, **fields):
        self.tab.handle_sql_result(sample_result(self.tab.current_sql_request_id, **fields))
        self.root.update()

    def test_workspace_fills_height_and_splitter_moves(self):
        self.assertGreater(self.tab.splitter.winfo_height(), self.tab.winfo_height() * .7)
        y = self.tab.splitter.sash_coord(0)[1]
        self.tab.splitter.sash_place(0, 0, y + 60);self.root.update()
        self.assertGreater(self.tab.splitter.sash_coord(0)[1], y)
        self.root.geometry('900x600');self.root.update();self.tab._apply_layout();self.root.update()
        self.assertEqual(int(self.tab.actions.grid_info()['row']), 2)
        self.assertGreater(self.tab.results_panel.winfo_height(), 90)

    def test_execute_selection_and_prevent_duplicate_requests(self):
        self.tab.sql_editor.delete('1.0','end');self.tab.sql_editor.insert('1.0', 'SELECT 1;\nSELECT 2;')
        text = self.tab.sql_editor._textbox;text.tag_add('sel', '2.0','2.end')
        self.tab.execute_sql();self.tab.execute_sql();self.tab.test_sql_connection()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['sql_text'], 'SELECT 2;')
        self.assertEqual(self.tab.execute_button.cget('state'), 'disabled')
        self.assertEqual(self.tab.stop_sql_button.cget('state'), 'normal')
        self.reply()
        self.assertFalse(self.tab.busy)
        self.assertEqual(self.tab.execute_button.cget('state'), 'normal')

    def test_stale_result_and_wrong_client_are_ignored(self):
        self.tab.execute_sql();rid = self.tab.current_sql_request_id
        self.tab.handle_sql_result(sample_result('OLD'))
        self.tab.handle_sql_result(sample_result(rid, client_code='OTHER'))
        self.tab.handle_sql_result(sample_result(rid, bo_connection_id=2))
        self.assertTrue(self.tab.busy)
        self.assertFalse(self.tab.results_panel.datasets)
        self.reply()
        self.tab.handle_sql_cancel_result({'client_code':'TEST','request_id':rid,'success':False,'message':'LATE'})
        self.assertNotIn('LATE',self.tab.sql_result_box.get('1.0','end'))

    def test_routing_error_restores_controls(self):
        self.tab.execute_sql()
        self.tab.handle_sql_error({'client_code':'TEST','request_id':self.tab.current_sql_request_id,'message':'Client offline'})
        self.assertFalse(self.tab.busy)
        self.assertEqual(self.tab.stop_sql_button.cget('state'),'disabled')
        self.assertEqual(self.tab.execute_button.cget('state'),'normal')

    def test_test_connection_state_and_cancel_requires_final_result(self):
        self.tab.test_sql_connection();rid=self.tab.current_sql_request_id
        self.assertEqual(self.tab.stop_sql_button.cget('state'),'disabled')
        self.tab.handle_sql_test_connection_result({'client_code':'TEST','request_id':rid,'bo_connection_id':1,'success':True,'database_name':'InitialTest'})
        self.tab.execute_sql();rid=self.tab.current_sql_request_id
        self.tab.stop_sql_execution();self.tab.stop_sql_execution()
        self.assertEqual(sum(item['type']=='sql_cancel' for item in self.sent),1)
        self.tab.handle_sql_cancel_result({'client_code':'TEST','request_id':rid,'success':False,'message':'Cancel failed'})
        self.assertEqual(self.tab.stop_sql_button.cget('state'),'normal')
        self.assertIn('Running',self.tab.status_label.cget('text'))
        self.tab.stop_sql_execution()
        self.tab.handle_sql_cancel_result({'client_code':'TEST','request_id':rid,'success':True,'message':'Cancel sent'})
        self.assertTrue(self.tab.busy)
        self.reply(success=False,error='Cancelled')
        self.assertFalse(self.tab.busy)

    def test_result_tables_duplicate_headers_copy_and_limits(self):
        self.tab.execute_sql();self.reply()
        panel=self.tab.results_panel;name=panel.selector.get();tree=panel.tables[name][1]
        self.assertEqual(len(tree['columns']),3)
        self.assertIn('Περιορισμένα',panel.caption.cget('text'))
        panel.copy_all()
        self.assertIn('Αθήνα',self.root.clipboard_get())
        tree.selection_set('0');panel.copy_selected()
        self.assertNotIn('tab',self.root.clipboard_get())
        panel.selector.set('Messages');panel.show('Messages')
        self.assertEqual(panel.export_button.cget('state'),'disabled')

    def test_large_result_copy_is_complete_before_display_finishes(self):
        self.tab.execute_sql()
        payload=sample_result(self.tab.current_sql_request_id,batches=[{'batch_index':1,'result_sets':[{'columns':['ID'],'rows':[[i] for i in range(500)]}]}])
        self.tab.handle_sql_result(payload)
        self.tab.results_panel.copy_all()
        self.assertIn('499',self.root.clipboard_get())
        self.tab.results_panel.clear();self.root.update()
        self.assertFalse(self.tab.results_panel.tables)

    def test_offline_missing_connection_and_invalid_timeout_do_not_send(self):
        self.tab.set_online(False);self.tab.execute_sql()
        self.assertFalse(self.sent)
        self.tab.set_online(True);self.tab.set_bo_values([]);self.tab.execute_sql()
        self.assertFalse(self.sent)
        self.tab.set_bo_values(['ID 1 - InitialTest'])
        self.tab.timeout_entry.delete(0,'end');self.tab.timeout_entry.insert(0,'abc');self.tab.execute_sql()
        self.assertFalse(self.sent)

    def test_failed_send_unlocks_and_disconnect_does_not_repeat_sql(self):
        self.tab.on_sql_execute_callback=lambda payload:False
        self.tab.execute_sql();self.assertFalse(self.tab.busy)
        self.tab.set_online(True)
        self.assertIn('Error',self.tab.status_label.cget('text'))
        self.tab.on_sql_execute_callback=self.sent.append
        self.tab.execute_sql();self.tab.set_online(False)
        self.assertFalse(self.tab.busy)
        self.tab.set_online(True)
        self.assertEqual(len(self.sent),1)
        self.assertIn('άγνωστη',self.tab.sql_result_box.get('1.0','end'))

    def test_file_load_save_csv_and_editor_highlight(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.sql';target=Path(folder)/'saved.sql';csv_path=Path(folder)/'data.csv'
            source.write_bytes("SELECT N'Αθήνα'; -- δοκιμή".encode('cp1253'))
            with patch('app.views.manage.sql_tab.filedialog.askopenfilename',return_value=str(source)):
                self.tab._load_sql_file()
            self.assertIn('Αθήνα',self.tab.sql_editor.get('1.0','end'))
            self.tab.editor_panel.highlight()
            self.assertTrue(self.tab.sql_editor._textbox.tag_ranges('keyword'))
            self.assertTrue(self.tab.sql_editor._textbox.tag_ranges('string'))
            with patch('app.views.manage.sql_tab.filedialog.asksaveasfilename',return_value=str(target)):
                self.tab.save_sql_file()
            self.assertIn('Αθήνα',target.read_text('utf-8'))
            self.tab.execute_sql();self.reply()
            with patch('app.views.manage.sql_results.filedialog.asksaveasfilename',return_value=str(csv_path)):
                self.tab.results_panel.export_csv()
            self.assertTrue(csv_path.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertIn('Αθήνα',csv_path.read_text('utf-8-sig'))

    def test_shortcut_only_applies_inside_ssms(self):
        text=self.tab.sql_editor._textbox;text.focus_force();self.root.update()
        text.event_generate('<F5>');self.root.update()
        self.assertEqual(len(self.sent),1)

    def test_manage_tab_row_is_weighted(self):
        from app.views.client_manage_window import ClientManageWindow
        window=ClientManageWindow(self.root,client={'client_code':'TEST','pc_name':'TEST','status':'online'})
        try:
            self.assertEqual(window.sql_tab.grid_rowconfigure(0)['weight'],1)
        finally:window.destroy()


if __name__ == '__main__':unittest.main()
