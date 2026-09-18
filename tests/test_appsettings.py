"""Δοκιμές απόκρυψης, επιλογής συνδέσεων και CLI χωρίς πραγματικό πελάτη."""

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from app.appsettings_presenter import AppSettingsPresenter as Presenter
from app.appsettings_cli import AppSettingsCLI


def sample_data():
    """Παρέχει τεχνητά δεδομένα που δεν προέρχονται από πελάτη."""
    return {'file_found': True, 'file_path': r'C:\Provider\appsettings.production.json',
            'last_read_at': '2026-09-18T12:30:00+03:00', 'selected_bo_connection_id': 1,
            'raw_json': {'password': 'RAW_PRIVATE'}, 'raw_text': 'RAW_PRIVATE',
            'appsettings_summary': {'AllowedHosts': '*', 'MaxRetries': 0,
                                    'MaxWaitTimePerInvoice': 15, 'initialDate': 20240101},
            'bo_connections': [
                {'ID': 1, 'DatabaseConnection': 'Server=PC-TEST;Database=InitialTest;User ID=PRIVATE_USER;Password="PRIVATE;PASS"',
                 'UserOID': 1, 'email': 'support@example.com', 'ClientAuth': 'PRIVATE_AUTH',
                 'subscriptionKey': 'PRIVATE_KEY', 'HasDatabaseUser': True, 'HasDatabasePassword': True},
                {'ID': 2, 'DatabaseConnection': 'Server=PC-TEST;Database=OtherTest;Integrated Security=True'}],
            'provider_connections': [{'ID': 1, 'BaseURL': 'https://user:PRIVATE_URL@provider.example/api?subscriptionKey=PRIVATE_QUERY',
                                      'OfflineURL': 'http://localhost:5000'}]}


class PresenterTests(unittest.TestCase):
    """Ελέγχει τη διαρροή μυστικών στα δεδομένα που τελικά προβάλλονται."""

    def test_no_secret_or_raw_payload_in_json(self):
        result = Presenter.json(sample_data())
        for secret in ('PRIVATE', 'RAW_PRIVATE', 'raw_json', 'raw_text'):
            self.assertNotIn(secret, result)
        self.assertIn('PC-TEST', result)
        self.assertIn('InitialTest', result)

    def test_masked_connection_handles_quoted_semicolon_and_equals(self):
        for value in ['Password="secret;rest";Server=PC', "Pwd='secret;rest';Database=DB",
                      'Password={secret;rest};Server=PC', 'uid=secret;pwd=secret=rest;Server=PC']:
            with self.subTest(value=value):
                safe = Presenter.masked_connection(value)
                self.assertNotIn('secret', safe)
                self.assertNotIn('rest', safe)

    def test_zero_empty_and_dates(self):
        self.assertEqual(Presenter.text(0), '0')
        self.assertEqual(Presenter.text(None), '—')
        self.assertEqual(Presenter.date(20240101), '01/01/2024')
        self.assertEqual(Presenter.date('invalid'), 'invalid')
        self.assertIn('UTC+03:00', Presenter.timestamp('2026-09-18T12:30:00+03:00'))

    def test_safe_data_is_idempotent_and_does_not_mutate_input(self):
        data = sample_data()
        safe = Presenter.safe_data(data)
        self.assertIs(safe['bo_connections'][0]['HasDatabasePassword'], True)
        self.assertEqual(Presenter.safe_data(safe), safe)
        self.assertEqual(data['bo_connections'][0]['ClientAuth'], 'PRIVATE_AUTH')

    def test_cli_filters_and_lists_connections(self):
        payload = {'success': True, 'appsettings': sample_data()}
        args = argparse.Namespace(bo_connection=2, list_connections=False)
        result = AppSettingsCLI.render(payload, args)
        self.assertEqual(result['selected_bo_connection_id'], 2)
        self.assertEqual(len(result['bo_connections']), 1)
        args.list_connections = True
        self.assertEqual(AppSettingsCLI.render(payload, args),
                         {'bo_connections': [{'ID': 2, 'DatabaseName': 'OtherTest'}]})
        args.bo_connection = 99
        with self.assertRaises(ValueError):
            AppSettingsCLI.render(payload, args)

    def test_cli_hides_server_error(self):
        with self.assertRaisesRegex(ValueError, 'Αποτυχία ανάκτησης'):
            AppSettingsCLI.render({'success': False, 'message': 'PRIVATE'},
                                  argparse.Namespace(bo_connection=None, list_connections=False))

    def test_cli_protocol_ignores_unrelated_messages(self):
        import websockets
        async def scenario():
            """Χρησιμοποιεί τοπικό προσωρινό WebSocket χωρίς παραγωγικό token."""
            async def handler(ws):
                self.assertEqual(json.loads(await ws.recv())['type'], 'authenticate')
                await ws.send(json.dumps({'type': 'clients_update'}))
                await ws.send(json.dumps({'type': 'dashboard_connected'}))
                self.assertEqual(json.loads(await ws.recv()),
                                 {'type': 'get_client_appsettings', 'client_code': 'TEST'})
                await ws.send(json.dumps({'type': 'client_appsettings_result', 'client_code': 'OTHER'}))
                await ws.send(json.dumps({'type': 'client_appsettings_result', 'client_code': 'TEST',
                                          'success': True, 'appsettings': sample_data()}))
            async with websockets.serve(handler, '127.0.0.1', 0) as server:
                port = server.sockets[0].getsockname()[1]
                config = SimpleNamespace(dashboard_token='FAKE', dashboard_websocket_url=f'ws://127.0.0.1:{port}')
                result = await AppSettingsCLI().request(config, 'TEST')
                self.assertTrue(result['success'])
        asyncio.run(scenario())


@unittest.skipUnless(importlib.util.find_spec('customtkinter') and
                     (os.name == 'nt' or os.environ.get('DISPLAY')), 'Απαιτεί οθόνη και CustomTkinter.')
class AppSettingsUITests(unittest.TestCase):
    """Ελέγχει πραγματικά widgets, προστασία πεδίων και αλλαγή μεγέθους."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.appsettings_tab import AppSettingsTab
        self.root = ctk.CTk()
        self.root.geometry('1350x850')
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.selected = Mock()
        self.refresh = Mock()
        self.tab = AppSettingsTab(self.root, self.selected, self.refresh)
        self.tab.grid(sticky='nsew')
        self.tab.set_bo_values(['ID 1 - InitialTest', 'ID 2 - OtherTest'], 'ID 1 - InitialTest')
        self.tab.set_data(sample_data(), {'ID': 1})
        self.root.update()
        self.tab._apply_layout()

    def tearDown(self):
        self.tab.destroy()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def test_readonly_fields_and_no_secrets(self):
        card = self.tab.detail_cards[0]
        self.assertEqual(card.fields['Database'].get(), 'InitialTest')
        self.assertEqual(card.fields['HasDatabasePassword'].get(), '***')
        self.assertEqual(card.fields['Database']._entry.cget('state'), 'readonly')
        card.fields['Database']._entry.insert(0, 'CHANGE')
        self.assertEqual(card.fields['Database'].get(), 'InitialTest')
        self.tab.copy_json()
        self.assertNotIn('PRIVATE', self.root.clipboard_get())

    def test_full_height_and_responsive_columns(self):
        self.assertGreater(self.tab.content.winfo_height(), self.tab.winfo_height() * .6)
        self.assertEqual(int(self.tab.detail_cards[1].grid_info()['column']), 1)
        self.root.geometry('800x700')
        self.root.update()
        self.tab._apply_layout()
        self.root.update()
        self.assertEqual(int(self.tab.detail_cards[1].grid_info()['column']), 0)
        self.assertEqual(int(self.tab.detail_cards[1].grid_info()['row']), 1)
        self.assertLessEqual(self.tab.detail_cards[0].winfo_width(), self.tab.winfo_width())

    def test_mode_switch_and_error_clears_stale_data(self):
        self.tab.toggle_mode()
        self.root.update()
        self.assertTrue(self.tab.details_box.winfo_ismapped())
        self.assertFalse(self.tab.content.winfo_ismapped())
        self.tab.set_text('Δεν υπάρχουν δεδομένα')
        self.assertNotIn('Provider', self.tab.path_entry.get())
        self.assertEqual(self.tab.details_box.get('1.0', 'end-1c'), '')
        self.assertEqual(self.tab.copy_button.cget('state'), 'disabled')
        self.assertFalse(self.tab.detail_cards)

    def test_missing_file_clears_connection_choice(self):
        self.tab.set_data({'file_found': False, 'file_path': r'C:\Missing.json'})
        self.assertEqual(self.tab.bo_connection_option.cget('state'), 'disabled')
        self.assertEqual(self.tab.badge.cget('text'), 'Δεν βρέθηκε αρχείο')
        self.assertEqual(self.tab.path_entry.get(), r'C:\Missing.json')

    def test_empty_connections_keep_summary_visible(self):
        self.tab.set_data({'file_found': True, 'bo_connections': [], 'provider_connections': []})
        self.assertEqual(len(self.tab.summary_cards), 4)
        self.assertEqual(self.tab.detail_cards[0].fields['empty'].get(), 'Δεν υπάρχουν BOConnections')

    def test_selection_and_refresh_callbacks(self):
        self.tab._cycle_bo(1)
        self.selected.assert_called_once_with('ID 2 - OtherTest')
        self.tab._handle_refresh()
        self.refresh.assert_called_once_with()
        self.tab.set_data(sample_data(), {'ID': 2})
        self.assertEqual(self.tab.detail_cards[0].fields['Database'].get(), 'OtherTest')

    def test_shortcut_is_scoped_and_bindings_are_removed(self):
        other = self.root.bind('<Control-j>', lambda event: None, add='+')
        entry = self.tab.path_entry._entry
        entry.focus_force()
        self.root.update()
        entry.event_generate('<Control-j>')
        self.root.update()
        self.assertEqual(self.tab.mode.get(), 'Ασφαλές JSON')
        ids = [binding for sequence, binding in self.tab._shortcut_ids]
        self.tab.destroy()
        self.assertIn(other, self.root.bind('<Control-j>'))
        for binding in ids:
            self.assertNotIn(binding, self.root.bind('<Control-j>'))
        self.tab = Mock()

    def test_manage_window_uses_full_height_and_syncs_selection(self):
        from app.views.client_manage_window import ClientManageWindow
        window = ClientManageWindow(self.root, client={'client_code': 'TEST', 'pc_name': 'TEST-PC'})
        try:
            window.geometry('1350x1000')
            window.tabs.set('AppSettings')
            window.handle_appsettings_result({'client_code': 'TEST', 'success': True, 'appsettings': sample_data()})
            self.root.update()
            self.assertEqual(window.appsettings_tab.grid_rowconfigure(0)['weight'], 1)
            window._on_database_bo_selected('ID 2 - OtherTest')
            self.assertEqual(window.appsettings_tab_view.get_selected_bo_value(), 'ID 2 - OtherTest')
            self.assertEqual(window.appsettings_tab_view.detail_cards[0].fields['Database'].get(), 'OtherTest')
        finally:
            window.destroy()


if __name__ == '__main__':
    unittest.main()
