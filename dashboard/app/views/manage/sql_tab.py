"""Χώρος εργασίας SSMS με ρυθμιζόμενο editor και πίνακες αποτελεσμάτων."""

import logging
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from app.sql_workspace import SqlFiles, SqlResultData
from app.ui.theme import COLORS, FONTS, card_style, primary_button_style, secondary_button_style, danger_button_style
from app.views.manage.sql_editor import SqlEditor
from app.views.manage.sql_results import SqlResults

logger = logging.getLogger(__name__)


class SqlTab(ctk.CTkFrame):
    """Διατηρεί το υπάρχον SQL πρωτόκολλο και συσχετίζει κάθε απάντηση με την ενεργή εκτέλεση."""

    def __init__(self, parent, client_code: str,
                 on_sql_execute_callback: Callable[[dict], bool | None] | None = None,
                 on_bo_selected_callback: Callable[[str], None] | None = None,
                 online: bool = True):
        super().__init__(parent, corner_radius=0, fg_color='transparent')
        self.client_code = client_code
        self.on_sql_execute_callback = on_sql_execute_callback
        self.on_bo_selected_callback = on_bo_selected_callback
        self.selected_bo_connection_id = None
        self.current_sql_request_id = ''
        self._active_bo_id = None
        self._active_kind = ''
        self._stop_requested = False
        self._online = online
        self._values = []
        self._layout_job = None
        self._initial_split = False
        self._bindings = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_ui()
        self._bind_shortcuts()
        self.bind('<Configure>', self._schedule_layout, add='+')
        self._update_buttons()

    @property
    def busy(self):
        """Δηλώνει εκτέλεση ή δοκιμή σύνδεσης που δεν έχει ακόμη ολοκληρωθεί."""
        return bool(self.current_sql_request_id)

    def _build_ui(self):
        """Δημιουργεί toolbar, κατακόρυφο splitter και σύντομη ένδειξη συντομεύσεων."""
        header = ctk.CTkFrame(self, **card_style())
        header.grid(row=0, column=0, padx=16, pady=(12, 10), sticky='ew')
        header.grid_columnconfigure(0, weight=1)
        self.header = header
        ctk.CTkLabel(header, text='SSMS · SQL Workspace', font=FONTS.subtitle,
                     anchor='w').grid(row=0, column=0, padx=18, pady=(12, 8), sticky='w')
        self.status_label = ctk.CTkLabel(header, text='Ready', font=FONTS.small,
                                        fg_color=COLORS.accent_soft, corner_radius=8, text_color=COLORS.accent)
        self.status_label.grid(row=0, column=1, padx=18, pady=(12, 8), sticky='e')
        self.connection_bar = ctk.CTkFrame(header, fg_color='transparent')
        self.connection_bar.grid(row=1, column=0, padx=18, pady=(0, 14), sticky='ew')
        self.connection_bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.connection_bar, text='BOConnection', font=FONTS.small,
                     text_color=COLORS.text_secondary).grid(row=0, column=0, padx=(0, 10))
        self.sql_bo_option = ctk.CTkOptionMenu(self.connection_bar, values=['No BOConnections'],
                                              command=self._on_sql_bo_selected, width=250,
                                              dynamic_resizing=False, fg_color=COLORS.surface_light,
                                              button_color=COLORS.accent, button_hover_color=COLORS.accent_hover)
        self.sql_bo_option.grid(row=0, column=1, sticky='ew')
        self.sql_bo_option.bind('<Up>', lambda event: self._cycle_bo(-1))
        self.sql_bo_option.bind('<Down>', lambda event: self._cycle_bo(1))
        self.actions = ctk.CTkFrame(header, fg_color='transparent')
        self.actions.grid(row=1, column=1, padx=(0, 18), pady=(0, 14), sticky='e')
        self.test_button = ctk.CTkButton(self.actions, text='Test connection', width=125, height=32,
                                        command=self.test_sql_connection, **secondary_button_style())
        self.test_button.grid(row=0, column=0, padx=(0, 6))
        self.load_button = ctk.CTkButton(self.actions, text='Open .sql', width=90, height=32,
                                        command=self._load_sql_file, **secondary_button_style())
        self.load_button.grid(row=0, column=1, padx=(0, 6))
        self.save_button = ctk.CTkButton(self.actions, text='Save .sql', width=90, height=32,
                                        command=self.save_sql_file, **secondary_button_style())
        self.save_button.grid(row=0, column=2, padx=(0, 10))
        ctk.CTkLabel(self.actions, text='Timeout (s)', font=FONTS.small,
                     text_color=COLORS.text_secondary).grid(row=0, column=3, padx=(0, 5))
        self.timeout_entry = ctk.CTkEntry(self.actions, width=56, height=32)
        self.timeout_entry.insert(0, '120')
        self.timeout_entry.grid(row=0, column=4, padx=(0, 10))
        self.execute_button = ctk.CTkButton(self.actions, text='Execute · F5', width=110, height=32,
                                           command=self.execute_sql, **primary_button_style())
        self.execute_button.grid(row=0, column=5, padx=(0, 6))
        self.stop_sql_button = ctk.CTkButton(self.actions, text='Stop', width=70, height=32,
                                            command=self.stop_sql_execution, **danger_button_style())
        self.stop_sql_button.grid(row=0, column=6)
        self.splitter = tk.PanedWindow(self, orient='vertical', bg=COLORS.surface_light,
                                       borderwidth=0, sashwidth=8, sashrelief='flat', opaqueresize=True)
        self.splitter.grid(row=1, column=0, padx=16, pady=(0, 8), sticky='nsew')
        self.editor_panel = SqlEditor(self.splitter)
        self.sql_editor = self.editor_panel.box
        self.results_panel = SqlResults(self.splitter)
        self.sql_result_box = self.results_panel.messages_box
        self.splitter.add(self.editor_panel, minsize=90, stretch='always')
        self.splitter.add(self.results_panel, minsize=100, stretch='always')
        ctk.CTkLabel(self, text='F5 Execute  ·  Alt+Break Stop  ·  Ctrl+O Open  ·  Ctrl+S Save  ·  Ctrl+T Test  ·  Ctrl+Shift+C Copy all  ·  Ctrl+Shift+E CSV',
                     font=FONTS.small, text_color=COLORS.text_muted, anchor='w').grid(
                         row=2, column=0, padx=20, pady=(0, 8), sticky='ew')

    def _schedule_layout(self, event=None):
        """Ομαδοποιεί τις αλλαγές μεγέθους πριν μετακινηθεί η toolbar."""
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(60, self._apply_layout)

    def _apply_layout(self):
        """Μεταφέρει τις ενέργειες σε δεύτερη γραμμή σε στενά παράθυρα."""
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = None
        wide = self.winfo_width() >= 1200
        self.connection_bar.grid_configure(columnspan=1 if wide else 2)
        self.actions.grid_configure(row=1 if wide else 2, column=1 if wide else 0,
                                    columnspan=1 if wide else 2, sticky='e' if wide else 'w',
                                    padx=(12, 18) if wide else (18, 18))
        if not self._initial_split and self.splitter.winfo_height() > 200:
            self.splitter.sash_place(0, 0, int(self.splitter.winfo_height() * .54))
            self._initial_split = True

    def set_bo_values(self, values: list[str], selected_value: str | None = None):
        """Ενημερώνει την κοινή επιλογή χωρίς να αποδίδει κρυφά ένα μη διαθέσιμο ID."""
        self._values = [value for value in values if self._extract_bo_id_from_option(value) is not None]
        safe = self._values or ['No BOConnections']
        self.sql_bo_option.configure(values=safe)
        self.sql_bo_option.set(selected_value if selected_value in safe else safe[0])
        self.selected_bo_connection_id = self._extract_bo_id_from_option(self.sql_bo_option.get())
        self._update_buttons()

    @staticmethod
    def _extract_bo_id_from_option(value: str):
        """Αναγνωρίζει επιλογές ID και ονόματος βάσης."""
        try:
            return int(value.split()[1])
        except (ValueError, IndexError):
            return None

    def _on_sql_bo_selected(self, value: str):
        """Συγχρονίζει τη βάση με το Manage window."""
        self.selected_bo_connection_id = self._extract_bo_id_from_option(value)
        logger.info('Αλλαγή επιλογής SSMS BOConnection.')
        if self.on_bo_selected_callback:
            self.on_bo_selected_callback(value)
        self._update_buttons()

    def _cycle_bo(self, step: int):
        """Επιτρέπει επιλογή βάσης από το πληκτρολόγιο όταν δεν εκτελείται αίτημα."""
        if self._values and not self.busy:
            index = self._values.index(self.sql_bo_option.get())
            value = self._values[(index + step) % len(self._values)]
            self.sql_bo_option.set(value)
            self._on_sql_bo_selected(value)
        return 'break'

    def _update_buttons(self):
        """Απενεργοποιεί επαναλαμβανόμενη εκτέλεση και ενέργειες χωρίς διαθέσιμη σύνδεση."""
        allowed = self._online and not self.busy and self.selected_bo_connection_id is not None
        for button in (self.execute_button, self.test_button):
            button.configure(state='normal' if allowed else 'disabled')
        self.sql_bo_option.configure(state='normal' if self._values and not self.busy else 'disabled')
        self.stop_sql_button.configure(state='normal' if self.busy and self._active_kind == 'sql_execute'
                                       and self._online and not self._stop_requested else 'disabled')
        if not self._online:
            self.status_label.configure(text='Client offline', text_color=COLORS.warning)
        elif not self.busy:
            self.status_label.configure(text='Ready' if self._values else 'Select connection', text_color=COLORS.accent)

    def set_online(self, online: bool):
        """Ενημερώνει την κατάσταση χωρίς αυτόματη επανάληψη προηγούμενου SQL."""
        if not online and self.busy:
            self.results_panel.set_messages('Η σύνδεση διακόπηκε πριν ληφθεί τελικό αποτέλεσμα. Η κατάσταση της απομακρυσμένης εκτέλεσης είναι άγνωστη.', append=True)
            self.current_sql_request_id = ''
            self._active_kind = ''
        self._online = online
        self._update_buttons()

    def _begin(self, kind: str, timeout: int, sql_text: str = ''):
        """Στέλνει ένα μόνο αίτημα και κρατά snapshot της βάσης που χρησιμοποιήθηκε."""
        if self.busy or not self._online or self.selected_bo_connection_id is None:
            return
        if not self.on_sql_execute_callback:
            self.results_panel.set_messages('Δεν υπάρχει διαθέσιμη σύνδεση για αποστολή SQL.')
            return
        self.current_sql_request_id = str(uuid.uuid4())
        self._active_bo_id = self.selected_bo_connection_id
        self._active_kind = kind
        self._stop_requested = False
        self.results_panel.clear()
        self.results_panel.set_messages(f"{'Εκτέλεση SQL' if sql_text else 'Δοκιμή σύνδεσης'} · BOConnection ID {self._active_bo_id}")
        self._update_buttons()
        self.status_label.configure(text=f'Running · ID {self._active_bo_id}', text_color=COLORS.info)
        payload = {'type': kind, 'request_id': self.current_sql_request_id, 'client_code': self.client_code,
                   'bo_connection_id': self._active_bo_id, 'timeout': timeout}
        if sql_text:
            payload['sql_text'] = sql_text
        try:
            sent = self.on_sql_execute_callback(payload)
            if sent is False:
                raise RuntimeError('not_sent')
            logger.info('Αποστολή SSMS αιτήματος. type=%s request_id=%s bo_id=%s', kind, self.current_sql_request_id, self._active_bo_id)
        except Exception:
            self.results_panel.set_messages('Το SQL αίτημα δεν στάλθηκε. Ελέγξτε τη σύνδεση Dashboard–Server.')
            self._finish(False)
            logger.error('Αποτυχία αποστολής SSMS αιτήματος.')

    def execute_sql(self):
        """Εκτελεί την επιλογή ή ολόκληρο το script, όπως δηλώνει η ένδειξη editor."""
        if self.busy:
            return
        sql = self.editor_panel.selected_or_all()
        if not sql:
            self.results_panel.set_messages('Το SQL κείμενο είναι κενό.')
            return
        try:
            timeout = int(self.timeout_entry.get())
            if not 1 <= timeout <= 3600:
                raise ValueError
        except ValueError:
            self.results_panel.set_messages('Το timeout πρέπει να είναι ακέραιος από 1 έως 3600 δευτερόλεπτα.')
            return
        self._begin('sql_execute', timeout, sql)

    def test_sql_connection(self):
        """Χρησιμοποιεί το υπάρχον αίτημα ελέγχου σύνδεσης με timeout 15s."""
        self._begin('sql_test_connection', 15)

    def stop_sql_execution(self):
        """Ζητά ακύρωση αλλά περιμένει τελικό SQL αποτέλεσμα πριν επιτρέψει νέα εκτέλεση."""
        if not self.busy or self._active_kind != 'sql_execute' or self._stop_requested or not self._online:
            return
        self._stop_requested = True
        self._update_buttons()
        self.status_label.configure(text='Stop requested', text_color=COLORS.warning)
        try:
            sent = self.on_sql_execute_callback({'type': 'sql_cancel', 'request_id': self.current_sql_request_id,
                                                'client_code': self.client_code})
            if sent is False:
                raise RuntimeError('not_sent')
            self.results_panel.set_messages('Στάλθηκε αίτημα ακύρωσης. Αναμονή τελικού αποτελέσματος.', append=True)
            logger.info('Αίτημα ακύρωσης SSMS. request_id=%s', self.current_sql_request_id)
        except Exception:
            self._stop_requested = False
            self._update_buttons()
            self.results_panel.set_messages('Το αίτημα ακύρωσης δεν στάλθηκε.', append=True)

    def _accept(self, payload: dict, kind: str = '') -> bool:
        """Απορρίπτει παλιές απαντήσεις και αποτελέσματα άλλου Client ή εκτέλεσης."""
        return bool(self.current_sql_request_id and payload.get('client_code') == self.client_code
                    and payload.get('request_id') == self.current_sql_request_id
                    and (not kind or kind == self._active_kind)
                    and (payload.get('bo_connection_id') is None or str(payload['bo_connection_id']) == str(self._active_bo_id)))

    def _finish(self, success: bool, detail: str = ''):
        """Επαναφέρει τα χειριστήρια μόνο μετά από τελικό αποτέλεσμα ή αποτυχία αποστολής."""
        self.current_sql_request_id = ''
        self._active_kind = ''
        self._stop_requested = False
        self._update_buttons()
        self.status_label.configure(text=('Completed' if success else 'Error') + detail,
                                    text_color=COLORS.success if success else COLORS.danger)

    def handle_sql_result(self, payload: dict):
        """Προβάλλει πίνακες και πραγματικά batch errors χωρίς να χάνει τα μερικά αποτελέσματα."""
        if not self._accept(payload, 'sql_execute'):
            return
        self.results_panel.render(payload)
        rows = sum(len(item.get('rows') or []) for item in self.results_panel.datasets.values())
        elapsed = payload.get('elapsed_ms')
        self._finish(not SqlResultData.failed(payload), f" · {rows} rows" + (f' · {elapsed} ms' if elapsed is not None else ''))
        logger.info('Ολοκλήρωση SSMS αποτελέσματος. rows=%s', rows)

    def handle_sql_error(self, payload: dict):
        """Αποκαθιστά και τα κουμπιά μετά από routing error, όπως offline Client."""
        if self._accept(payload):
            self.results_panel.set_messages('SQL ERROR:\n' + str(payload.get('message') or 'Unknown SQL error'))
            self._finish(False)

    def handle_sql_test_connection_result(self, payload: dict):
        """Εμφανίζει στοιχεία και διάρκεια της δοκιμής σύνδεσης."""
        if not self._accept(payload, 'sql_test_connection'):
            return
        labels = [('BOConnection ID', 'bo_connection_id'), ('Server', 'server_name'), ('Database', 'database_name'),
                  ('Login', 'login_name'), ('Driver', 'driver'), ('Elapsed ms', 'elapsed_ms'), ('Error', 'error')]
        self.results_panel.set_messages('SQL Connection Test\n' + '\n'.join(f'{label}: {payload.get(key) if payload.get(key) is not None else "—"}' for label, key in labels))
        self._finish(bool(payload.get('success')))
        logger.info('Ολοκλήρωση ελέγχου SSMS σύνδεσης. success=%s', bool(payload.get('success')))

    def handle_sql_cancel_result(self, payload: dict):
        """Διαχωρίζει την επιβεβαίωση αιτήματος ακύρωσης από το τελικό αποτέλεσμα του query."""
        if self._accept(payload, 'sql_execute'):
            self.results_panel.set_messages('Cancel: ' + str(payload.get('message') or payload.get('success')), append=True)
            if not payload.get('success'):
                self._stop_requested = False
                self._update_buttons()

    def _load_sql_file(self):
        """Φορτώνει script χωρίς εκτέλεση και κρατά την εστίαση στο Manage window."""
        owner = self.winfo_toplevel()
        path = filedialog.askopenfilename(parent=owner, title='Open SQL script', filetypes=[('SQL', '*.sql'), ('All files', '*.*')])
        owner.after_idle(owner.focus_force)
        if path:
            try:
                content, encoding = SqlFiles.read(Path(path))
                self.sql_editor.delete('1.0', 'end'); self.sql_editor.insert('1.0', content)
                self.results_panel.set_messages(f'Φορτώθηκε SQL αρχείο · Encoding: {encoding}', append=True)
                logger.info('Φόρτωση SQL αρχείου. encoding=%s', encoding)
            except (OSError, UnicodeError):
                self.results_panel.set_messages('Αποτυχία ανάγνωσης SQL αρχείου.', append=True)
                logger.error('Αποτυχία ανάγνωσης SQL αρχείου.')

    def save_sql_file(self):
        """Αποθηκεύει ολόκληρο το script ως UTF-8, ανεξάρτητα από την επιλογή κειμένου."""
        owner = self.winfo_toplevel()
        path = filedialog.asksaveasfilename(parent=owner, title='Save SQL script', defaultextension='.sql', filetypes=[('SQL', '*.sql')])
        owner.after_idle(owner.focus_force)
        if path:
            try:
                Path(path).write_text(self.sql_editor.get('1.0', 'end-1c'), encoding='utf-8')
                logger.info('Αποθήκευση SQL script.')
            except OSError:
                self.results_panel.set_messages('Αποτυχία αποθήκευσης SQL αρχείου.', append=True)
                logger.error('Αποτυχία αποθήκευσης SQL αρχείου.')

    @staticmethod
    def _read_sql_file_with_fallback(path):
        """Διατηρεί την προηγούμενη δημόσια διεπαφή ανάγνωσης αρχείων."""
        return SqlFiles.read(path)

    def _set_sql_result_text(self, text):
        """Διατηρεί την προηγούμενη διεπαφή μηνυμάτων."""
        self.results_panel.set_messages(text)

    def _bind_shortcuts(self):
        """Ενεργοποιεί συντομεύσεις μόνο όταν η εστίαση ανήκει στην καρτέλα SSMS."""
        top = self.winfo_toplevel()
        actions = {'<F5>': self.execute_sql, '<Control-Return>': self.execute_sql, '<Alt-Cancel>': self.stop_sql_execution,
                   '<Alt-Pause>': self.stop_sql_execution, '<Alt-Break>': self.stop_sql_execution,
                   '<Control-o>': self._load_sql_file, '<Control-s>': self.save_sql_file, '<Control-t>': self.test_sql_connection,
                   '<Control-Shift-C>': self.results_panel.copy_all, '<Control-Shift-E>': self.results_panel.export_csv,
                   '<Control-b>': self.sql_bo_option._canvas.focus_set,
                   '<Control-r>': self.results_panel.selector._canvas.focus_set,
                   '<Control-m>': self.results_panel.show_messages,
                   '<Control-Shift-P>': self.sql_editor._textbox.focus_set,
                   '<Alt-Up>': lambda: self._move_split(-40), '<Alt-Down>': lambda: self._move_split(40)}
        for sequence, action in actions.items():
            def handle(event, callback=action):
                """Δεν παρεμβαίνει στο Terminal ή σε άλλες καρτέλες."""
                widget = top.focus_get()
                while widget is not None:
                    if widget is self:
                        callback(); return 'break'
                    widget = getattr(widget, 'master', None)
            self._bindings.append((sequence, top.bind(sequence, handle, add='+')))

    def _move_split(self, offset: int):
        """Αλλάζει την κατανομή editor/αποτελεσμάτων και από πληκτρολόγιο."""
        current = self.splitter.sash_coord(0)[1]
        target = max(90, min(self.splitter.winfo_height() - 108, current + offset))
        self.splitter.sash_place(0, 0, target)

    def destroy(self):
        """Αφαιρεί callbacks και bindings πριν κλείσει η καρτέλα."""
        if self._layout_job:
            self.after_cancel(self._layout_job)
        top = self.winfo_toplevel()
        for sequence, binding in self._bindings:
            top.unbind(sequence, binding)
        self._bindings.clear()
        super().destroy()
