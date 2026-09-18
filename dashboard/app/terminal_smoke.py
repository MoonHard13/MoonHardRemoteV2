"""Έλεγχος του συσκευασμένου Terminal σε καθαρό φάκελο, χωρίς σύνδεση σε πελάτη."""

import json
from pathlib import Path

import customtkinter as ctk

from app.views.manage.terminal_tab import TerminalTab


class TerminalSmokeTest:
    """Επαληθεύει ότι το EXE περιέχει το πραγματικό widget και τα απαιτούμενα resources."""

    @staticmethod
    def run(report_path: str) -> int:
        """Επιστρέφει αναφορά ελέγχου χωρίς δικτύωση ή μεταβολές στο remote σύστημα."""
        root = None
        tab = None
        try:
            root = ctk.CTk()
            root.geometry('1250x850')
            root.grid_columnconfigure(0, weight=1)
            root.grid_rowconfigure(0, weight=1)
            sent = []
            tab = TerminalTab(root, 'SMOKE_TEST', sent.append)
            tab.grid(row=0, column=0, sticky='nsew')
            root.update()
            assert sent[-1]['type'] == 'terminal_session_open'
            tab.handle_terminal_result({'type':'terminal_session_result', 'operation':'open', 'success':True,
                'client_code':'SMOKE_TEST', 'session_id':tab.session_id, 'request_id':tab.request_id,
                'current_directory':'C:\\SmokeTest', 'exit_code':0})
            box = tab.output_box
            prefix = box.text.get('1.0', 'input_start')
            box.text.insert('1.0', 'whoami')
            assert box.command() == 'whoami'
            assert box.text.get('1.0', 'input_start') == prefix
            assert box.winfo_height() > 550
            tab.send_terminal_command()
            assert sent[-1]['type'] == 'terminal_session_command'
            assert not box.accept_input
            result = {'success':True, 'protected_prompt':True, 'inline_command':True,
                      'terminal_height':box.winfo_height()}
            code = 0
        except Exception as exc:
            result = {'success':False, 'exception':type(exc).__name__, 'message':str(exc)}
            code = 1
        finally:
            if root:
                if tab:
                    tab.destroy()
                for job in root.tk.call('after', 'info'):
                    root.after_cancel(job)
                root.destroy()
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return code
