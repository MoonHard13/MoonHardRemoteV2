"""Πραγματικές δοκιμές Tk για προστασία output, πληκτρολόγηση και layout."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))


@unittest.skipUnless(importlib.util.find_spec('customtkinter') and (os.name == 'nt' or os.environ.get('DISPLAY')),
                     'Απαιτεί CustomTkinter και διαθέσιμη οθόνη.')
class TerminalUITests(unittest.TestCase):
    """Χρησιμοποιεί το πραγματικό widget μαζί με τον Tcl proxy."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.terminal_tab import TerminalTab
        self.root = ctk.CTk()
        self.root.geometry('1250x850')
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.sent = []
        self.tab = TerminalTab(self.root, 'CLIENT01', self.sent.append, self.sent.append)
        self.tab.grid(sticky='nsew')
        self.root.update()
        self.reply(operation='open')
        self.box = self.tab.output_box
        self.text = self.box.text

    def tearDown(self):
        self.tab.destroy()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()

    def reply(self, **fields):
        """Ολοκληρώνει με συσχετισμένο αποτέλεσμα την τρέχουσα remote ενέργεια."""
        self.tab.handle_terminal_result({'type':'terminal_session_result', 'success': True,
            'client_code':'CLIENT01', 'session_id':self.tab.session_id, 'request_id':self.tab.request_id,
            'exit_code':0, 'current_directory':'C:\\Users\\support', **fields})

    def test_terminal_uses_available_height(self):
        self.assertGreater(self.box.winfo_height(), self.tab.winfo_height() * .6)
        self.assertFalse(hasattr(self.tab, 'command_entry'))

    def test_insert_in_history_moves_to_active_command(self):
        prefix = self.text.get('1.0', 'input_start')
        self.text.insert('1.0', 'ipconfig')
        self.assertEqual(self.text.get('1.0', 'input_start'), prefix)
        self.assertEqual(self.box.command(), 'ipconfig')

    def test_delete_and_replace_cannot_modify_prompt_or_history(self):
        prefix = self.text.get('1.0', 'input_start')
        self.box.set_command('whoami')
        self.text.delete('1.0', 'end')
        self.assertEqual(self.text.get('1.0', 'input_start'), prefix)
        self.assertEqual(self.box.command(), '')
        self.text.replace('1.0', 'end', 'echo first\necho second')
        self.assertEqual(self.text.get('1.0', 'input_start'), prefix)
        self.assertNotIn('\n', self.box.command())

    def test_paste_flattens_newlines_without_execution(self):
        self.box.clipboard_clear()
        self.box.clipboard_append('echo first\r\necho second')
        self.text.mark_set('insert', '1.0')
        self.box.paste()
        self.assertEqual(self.box.command(), 'echo first echo second')
        self.assertEqual(len(self.sent), 1)

    def test_output_preserves_draft_and_prefix(self):
        self.box.set_command('draft')
        self.box.append('System message\n', 'system')
        self.assertEqual(self.box.command(), 'draft')
        self.assertTrue(self.text.get('1.0', 'end-1c').endswith('C:\\Users\\support> draft'))

    def test_running_input_is_protected_and_result_restores_prompt(self):
        self.box.set_command('whoami')
        self.tab.send_terminal_command()
        before = self.text.get('1.0', 'end')
        self.text.insert('end', 'accidental')
        self.text.delete('1.0', 'end')
        self.assertEqual(self.text.get('1.0', 'end'), before)
        self.assertEqual(self.sent[-1]['type'], 'terminal_session_command')
        self.assertTrue(self.tab.running)
        self.reply(operation='command', duration_seconds=.25)
        self.assertTrue(self.box.accept_input)
        self.assertFalse(self.tab.running)
        self.assertEqual(self.box.command(), '')

    def test_history_restores_draft(self):
        self.tab.command_history = ['whoami', 'ipconfig']
        self.box.set_command('unfinished')
        self.tab._show_previous_command()
        self.assertEqual(self.box.command(), 'ipconfig')
        self.tab._show_previous_command()
        self.assertEqual(self.box.command(), 'whoami')
        self.tab._show_next_command()
        self.tab._show_next_command()
        self.assertEqual(self.box.command(), 'unfinished')

    def test_clear_keeps_remote_session_and_draft(self):
        sid = self.tab.session_id
        self.box.set_command('draft')
        self.tab.clear_terminal()
        self.assertEqual(self.box.command(), 'draft')
        self.assertEqual(sid, self.tab.session_id)
        self.assertEqual(len(self.sent), 1)

    def test_old_result_does_not_change_current_session(self):
        self.tab.handle_terminal_result({'type':'terminal_session_result', 'success':False,
            'client_code':'CLIENT01', 'session_id':str(uuid4()), 'request_id':str(uuid4()), 'message':'late'})
        self.assertTrue(self.tab.ready)

    def test_idle_client_disconnect_locks_input(self):
        self.tab.handle_terminal_result({'type':'terminal_session_result', 'success':False,
            'client_code':'CLIENT01', 'session_id':self.tab.session_id, 'request_id':'',
            'session_closed':True, 'message':'Client disconnected'})
        self.assertFalse(self.box.accept_input)
        self.assertFalse(self.tab.ready)

    def test_dashboard_disconnect_locks_input(self):
        self.tab.connection_lost()
        self.assertFalse(self.box.accept_input)
        self.assertFalse(self.tab.ready)

    def test_late_autocomplete_does_not_overwrite_edit(self):
        self.box.set_command('cd lo')
        self.tab._request_terminal_autocomplete()
        request = self.sent[-1]
        self.box.set_command('whoami')
        self.tab.handle_terminal_autocomplete_result({**request,'matches':[{'insert_value':'logs\\'}]})
        self.assertEqual(self.box.command(), 'whoami')

    def test_autocomplete_cycles_quoted_paths(self):
        self.box.set_command('cd "Program F')
        self.tab._request_terminal_autocomplete()
        request = self.sent[-1]
        self.tab.handle_terminal_autocomplete_result({**request,'matches':[
            {'insert_value':'"Program Files\\"'}, {'insert_value':'"Program Files (x86)\\"'}]})
        self.assertEqual(self.box.command(), 'cd "Program Files\\"')
        self.tab._request_terminal_autocomplete()
        self.assertEqual(self.box.command(), 'cd "Program Files (x86)\\"')


if __name__ == '__main__':
    unittest.main()
