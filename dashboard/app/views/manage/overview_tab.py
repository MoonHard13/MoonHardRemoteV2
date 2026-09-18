"""Overview με κάρτες, ζωντανά metadata και διαχείριση Client."""

import json
import logging
from typing import Callable
import customtkinter as ctk
from app.overview_presenter import OverviewPresenter
from app.ui.theme import COLORS, FONTS, card_style, primary_button_style, secondary_button_style, danger_button_style

logger = logging.getLogger(__name__)


class OverviewField(ctk.CTkFrame):
    """Επιλέξιμη τιμή μόνο για ανάγνωση, με σταθερό label."""

    def __init__(self, parent, label):
        super().__init__(parent, fg_color='transparent')
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, height=20, font=FONTS.small, text_color=COLORS.text_secondary,
                     anchor='w').grid(row=0, column=0, sticky='ew')
        self.entry = ctk.CTkEntry(self, height=32, font=FONTS.body, border_width=0,
                                 fg_color=COLORS.surface_light, text_color=COLORS.text_primary)
        self.entry.grid(row=1, column=0, sticky='ew')
        self.set('—')

    def set(self, value):
        """Δεν αλλάζει άσκοπα την επιλογή κειμένου σε κάθε heartbeat."""
        text = '—' if value is None or value == '' else str(value)
        if self.entry.get() != text:
            self.entry.configure(state='normal')
            self.entry.delete(0, 'end');self.entry.insert(0, text)
            self.entry.configure(state='readonly')


class TokenResetDialog(ctk.CTkToplevel):
    """Η υπάρχουσα επιβεβαίωση RESET ανήκει στο σωστό Manage window."""

    def __init__(self, owner):
        super().__init__(owner)
        self.answer = None
        self.title('Reset Client Token');self.geometry('450x220');self.resizable(False, False)
        self.configure(fg_color=COLORS.background);self.transient(owner)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text='Confirm token reset', font=FONTS.subtitle,
                     text_color=COLORS.text_primary).grid(row=0, column=0, columnspan=2, padx=20, pady=(18, 8), sticky='w')
        ctk.CTkLabel(self, text='Ο Client θα αποσυνδεθεί και θα δημιουργήσει νέο token.\nΠληκτρολογήστε RESET για επιβεβαίωση.',
                     font=FONTS.body, justify='left', text_color=COLORS.text_secondary).grid(row=1, column=0, columnspan=2, padx=20, sticky='w')
        self.entry = ctk.CTkEntry(self, placeholder_text='RESET', height=34)
        self.entry.grid(row=2, column=0, columnspan=2, padx=20, pady=12, sticky='ew')
        ctk.CTkButton(self, text='Cancel', command=self._cancel, **secondary_button_style()).grid(row=3, column=0, padx=20, sticky='w')
        ctk.CTkButton(self, text='Reset token', command=self._confirm, **danger_button_style()).grid(row=3, column=1, padx=20, sticky='e')
        self.entry.bind('<Return>', lambda event:self._confirm())
        self.bind('<Escape>', lambda event:self._cancel());self.protocol('WM_DELETE_WINDOW', self._cancel)
        self._activation_job = self.after(80, self._activate)

    def _activate(self):
        """Περιορίζει το grab μόνο στην επιβεβαίωση, όχι στο Manage window."""
        self._activation_job = None
        self.grab_set();self.entry.focus_force()

    def _confirm(self):
        """Κλείνει μόνο όταν έχει πληκτρολογηθεί η απαιτούμενη λέξη."""
        if self.entry.get() == 'RESET':
            self.answer = 'RESET';self.destroy()
        else:
            self.entry.configure(border_color=COLORS.danger)

    def _cancel(self):
        """Ακυρώνει χωρίς αποστολή αιτήματος."""
        self.destroy()

    def destroy(self):
        """Ακυρώνει καθυστερημένη εστίαση όταν κλείσει αμέσως το dialog."""
        if getattr(self,'_activation_job',None):self.after_cancel(self._activation_job)
        super().destroy()

    def get_input(self):
        """Επιστρέφει την απάντηση μετά το κλείσιμο του dialog."""
        self.wait_window();return self.answer


class OverviewTab(ctk.CTkFrame):
    """Παρουσιάζει ασφαλή metadata και δεν αντικαθιστά μη αποθηκευμένο rename σε heartbeat."""

    def __init__(self, parent, client: dict,
                 on_rename_callback: Callable[[str, str], bool | None] | None = None,
                 on_reset_token_callback: Callable[[str], bool | None] | None = None):
        super().__init__(parent, corner_radius=0, fg_color='transparent')
        self.client = client
        self.client_code = client.get('client_code', '')
        self.on_rename_callback = on_rename_callback
        self.on_reset_token_callback = on_reset_token_callback
        self._saved_name = OverviewPresenter.safe_data(client)['display_name']
        self._pending_name = None
        self._name_job = self._reset_job = self._layout_job = None
        self._reset_pending = False
        self._dashboard_online = True
        self._bindings = []
        self.fields = {}
        self.grid_columnconfigure(0, weight=1);self.grid_rowconfigure(1, weight=1)
        self._build_ui();self.update_client_data(client);self._bind_shortcuts()
        self.bind('<Configure>', self._schedule_layout, add='+')

    @property
    def name_pending(self):
        """Δείχνει αν αναμένεται επιβεβαίωση αλλαγής ονόματος."""
        return self._pending_name is not None

    def _card(self, parent, title, description):
        """Κοινός τίτλος και περιγραφή για όλες τις ενότητες."""
        card = ctk.CTkFrame(parent, **card_style());card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=FONTS.section_title,
                     text_color=COLORS.text_primary, anchor='w').grid(row=0, column=0, padx=18, pady=(16, 2), sticky='ew')
        ctk.CTkLabel(card, text=description, font=FONTS.small, text_color=COLORS.text_secondary,
                     anchor='w').grid(row=1, column=0, padx=18, pady=(0, 12), sticky='ew')
        return card

    def _build_ui(self):
        """Δύο στήλες στο μεγάλο παράθυρο και μία με κύλιση στο μικρό."""
        bar = ctk.CTkFrame(self, fg_color='transparent');bar.grid(row=0, column=0, padx=18, pady=(14, 10), sticky='ew')
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text='Overview', font=FONTS.subtitle,
                     text_color=COLORS.text_primary).grid(row=0, column=0, sticky='w')
        self.status_badge = ctk.CTkLabel(bar, text='Unknown', width=90, height=28, corner_radius=8)
        self.status_badge.grid(row=0, column=1, padx=12)
        ctk.CTkButton(bar, text='Copy details', width=110, height=30,
                      command=self.copy_details, **secondary_button_style()).grid(row=0, column=2)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color='transparent')
        self.scroll.grid(row=1, column=0, padx=10, pady=(0, 10), sticky='nsew')
        self.scroll.grid_columnconfigure(0, weight=3);self.scroll.grid_columnconfigure(1, weight=2)
        self.left_stack = ctk.CTkFrame(self.scroll,fg_color='transparent')
        self.right_stack = ctk.CTkFrame(self.scroll,fg_color='transparent')
        for stack in (self.left_stack,self.right_stack):stack.grid_columnconfigure(0,weight=1)
        self.identity_card = self._card(self.left_stack, 'Computer & connection', 'Στοιχεία του επιλεγμένου Client')
        identity = ctk.CTkFrame(self.identity_card, fg_color='transparent')
        identity.grid(row=2, column=0, padx=18, pady=(0, 18), sticky='ew')
        identity.grid_columnconfigure((0, 1), weight=1)
        for index, (key, label) in enumerate([('display_name','Display name'),('pc_name','Computer'),
            ('username','Windows user'),('group_name','Group'),('client_code','Client code'),
            ('last_seen','Last seen · local time'),('connection','Live connection')]):
            field = OverviewField(identity, label);self.fields[key] = field
            if key in ('client_code', 'last_seen', 'connection'):
                field.grid(row=index - 2, column=0, columnspan=2, pady=4, sticky='ew')
            else:
                field.grid(row=index//2, column=index%2, padx=(0, 6) if index%2==0 else (6, 0), pady=4, sticky='ew')
        self.versions_card = self._card(self.left_stack, 'Application versions', 'Εκδόσεις που ανέφερε ο Client')
        versions = ctk.CTkFrame(self.versions_card, fg_color='transparent')
        versions.grid(row=2, column=0, padx=18, pady=(0, 18), sticky='ew');versions.grid_columnconfigure((0, 1), weight=1)
        for index, (key, label) in enumerate([('app_version','MoonHard Client'),('amv_version','AMV'),
                                           ('bo_version','Back Office'),('etp_version','Tax Provider'),('aws_version','Web Service')]):
            field = OverviewField(versions, label);self.fields[key] = field
            field.grid(row=index//2, column=index%2, padx=(0, 6) if index%2==0 else (6, 0), pady=4, sticky='ew')
        self.rename_card = self._card(self.right_stack, 'Client name', 'Αναγνωρίσιμο όνομα στο Dashboard')
        self.rename_entry = ctk.CTkEntry(self.rename_card, height=38, placeholder_text='Friendly name',
            fg_color=COLORS.surface_light,border_color=COLORS.border,text_color=COLORS.text_primary)
        self.rename_entry.grid(row=2, column=0, padx=18, pady=(0, 10), sticky='ew');self.rename_entry.insert(0, self._saved_name)
        buttons = ctk.CTkFrame(self.rename_card, fg_color='transparent');buttons.grid(row=3, column=0, padx=18, sticky='ew')
        buttons.grid_columnconfigure(0, weight=1)
        self.rename_button = ctk.CTkButton(buttons, text='Save name', command=self._save_name, **primary_button_style())
        self.rename_button.grid(row=0, column=0, padx=(0, 8), sticky='ew')
        ctk.CTkButton(buttons, text='Revert', width=80, command=self.revert_name,
                      **secondary_button_style()).grid(row=0, column=1)
        self.name_status_label = ctk.CTkLabel(self.rename_card, text='Enter για αποθήκευση · Esc για επαναφορά',
            font=FONTS.small, text_color=COLORS.text_muted, justify='left', anchor='w', wraplength=320)
        self.name_status_label.grid(row=4, column=0, padx=18, pady=(8, 16), sticky='ew')
        self.rename_entry.bind('<Return>', lambda event:self._save_name())
        self.rename_entry.bind('<Escape>', lambda event:self.revert_name())
        self.security_card = self._card(self.right_stack, 'Security', 'Διαχείριση της ταυτότητας σύνδεσης')
        self.security_description = ctk.CTkLabel(self.security_card,
            text='Το reset token αποσυνδέει τον Client και απαιτεί επανεγγραφή με νέο token. Χρησιμοποιήστε το για πρόβλημα ταυτότητας ή πιθανή παραβίαση.',
            font=FONTS.body, text_color=COLORS.text_secondary, justify='left', anchor='w', wraplength=320)
        self.security_description.grid(row=2, column=0, padx=18, pady=(0, 14), sticky='ew')
        self.reset_token_button = ctk.CTkButton(self.security_card, text='Reset client token',
            command=self._reset_client_token, **danger_button_style())
        self.reset_token_button.grid(row=3, column=0, padx=18, sticky='ew')
        self.security_status_label = ctk.CTkLabel(self.security_card, text='Απαιτείται επιβεβαίωση RESET.',
            font=FONTS.small, text_color=COLORS.text_muted, justify='left', anchor='w', wraplength=320)
        self.security_status_label.grid(row=4, column=0, padx=18, pady=(8, 16), sticky='ew')
        self._apply_layout()

    def _schedule_layout(self, event=None):
        """Συγχωνεύει διαδοχικά resize events."""
        if self._layout_job:self.after_cancel(self._layout_job)
        self._layout_job = self.after(60, self._apply_layout)

    def _apply_layout(self):
        """Αλλάζει μόνο την τοποθέτηση των υπαρχόντων widgets."""
        self._layout_job = None
        wide = self.winfo_width() >= 1000
        self.scroll.grid_columnconfigure(1, weight=2 if wide else 0)
        self.left_stack.grid(row=0,column=0,padx=(4,8) if wide else 4,sticky='new')
        self.right_stack.grid(row=0 if wide else 1,column=1 if wide else 0,padx=(8,4) if wide else 4,sticky='new')
        for index,card in enumerate((self.identity_card,self.versions_card,self.rename_card,self.security_card)):
            card.grid(row=index%2,column=0,pady=(0,12),sticky='ew')
        width = max(240, (self.winfo_width()-90)*.4 if wide else self.winfo_width()-100)
        for label in (self.name_status_label,self.security_description,self.security_status_label):
            label.configure(wraplength=int(width))

    def update_client_data(self, client):
        """Ενημερώνει live πεδία και προστατεύει draft ονόματος από heartbeat."""
        if not client or (client.get('client_code') and client['client_code'] != self.client_code):return
        data = OverviewPresenter.safe_data(client);name = data['display_name']
        current = self.rename_entry.get()
        if current != name and (current == self._saved_name or (self._pending_name == name and current == self._pending_name)):
            self.rename_entry.delete(0, 'end');self.rename_entry.insert(0, name)
        self._saved_name = name;self.client = data
        if self._pending_name == name:self.handle_rename_result({'type':'rename_client_success','client':data})
        for key, field in self.fields.items():
            if key == 'connection':
                value = 'Connected' if data['ws_connected'] is True else 'Disconnected' if data['ws_connected'] is False else 'Not reported'
                if not self._dashboard_online:value = 'Unknown · Dashboard disconnected'
            elif key == 'last_seen':value = OverviewPresenter.last_seen(data[key])
            else:value = data.get(key)
            field.set(value)
        status = str(data.get('status') or 'Unknown').lower()
        online = status == 'online'
        if not self._dashboard_online:status = 'stale'
        online = online and self._dashboard_online
        self.status_badge.configure(text=status.capitalize(), text_color=COLORS.success if online else COLORS.warning,
                                     fg_color=COLORS.success_soft if online else COLORS.warning_soft)

    def set_dashboard_online(self,online):
        """Απενεργοποιεί αποστολές και δηλώνει παλιά metadata μετά από αποσύνδεση."""
        self._dashboard_online = online
        if not online:
            if self._name_job:self.after_cancel(self._name_job)
            if self.name_pending:self._name_timeout()
            if self._reset_job:self.after_cancel(self._reset_job)
            if self._reset_pending:self._reset_timeout()
        self.rename_button.configure(state='normal' if online and not self.name_pending else 'disabled')
        self.reset_token_button.configure(state='normal' if online and not self._reset_pending else 'disabled')
        self.update_client_data(self.client)

    def copy_details(self):
        """Αντιγράφει μόνο ασφαλή metadata, ποτέ credentials."""
        self.clipboard_clear();self.clipboard_append(json.dumps(OverviewPresenter.safe_data(self.client),ensure_ascii=False,indent=2))
        logger.info('Αντιγραφή Overview metadata. client_code=%s',self.client_code)

    def revert_name(self):
        """Επαναφέρει το τελευταίο επιβεβαιωμένο όνομα χωρίς αποστολή."""
        self.rename_entry.delete(0,'end');self.rename_entry.insert(0,self._saved_name)
        if not self.name_pending:self.name_status_label.configure(text='Επαναφέρθηκε το αποθηκευμένο όνομα.',text_color=COLORS.text_muted)
        logger.info('Επαναφορά Overview draft. client_code=%s',self.client_code)
        return 'break'

    def _save_name(self):
        """Αποστέλλει μία αλλαγή και εμφανίζει πραγματική επιβεβαίωση."""
        if self.name_pending or not self._dashboard_online:return 'break'
        try:
            name = OverviewPresenter.validate_name(self.rename_entry.get())
            if name == self._saved_name:
                self.name_status_label.configure(text='Το όνομα είναι ήδη αποθηκευμένο.',text_color=COLORS.text_muted);return 'break'
            if not self.on_rename_callback or self.on_rename_callback(self.client_code,name) is False:raise RuntimeError('not_sent')
            self._pending_name = name;self.rename_button.configure(state='disabled')
            self.name_status_label.configure(text='Αναμονή επιβεβαίωσης αποθήκευσης…',text_color=COLORS.info)
            self._name_job = self.after(30000,self._name_timeout)
            logger.info('Αίτημα rename Overview. client_code=%s',self.client_code)
        except Exception as exc:
            self.name_status_label.configure(text=str(exc) if isinstance(exc,ValueError) else 'Το αίτημα δεν στάλθηκε. Ελέγξτε τη σύνδεση Dashboard.',text_color=COLORS.danger)
            logger.warning('Αποτυχία rename Overview. client_code=%s exception_type=%s',self.client_code,type(exc).__name__)
        return 'break'

    def _name_timeout(self):
        """Δεν δηλώνει επιτυχία όταν δεν έχει φτάσει επιβεβαίωση."""
        self._name_job = None;self._pending_name = None;self.rename_button.configure(state='normal')
        self.name_status_label.configure(text='Δεν επιβεβαιώθηκε η αλλαγή. Ελέγξτε το αποθηκευμένο όνομα πριν επαναλάβετε.',text_color=COLORS.warning)

    def handle_rename_result(self,payload):
        """Συσχετίζει επιτυχία με Client και διατηρεί τυχόν νέο draft."""
        client = payload.get('client') or {}
        if client.get('client_code') not in (None,self.client_code):return
        if not self.name_pending:return
        if self._name_job:self.after_cancel(self._name_job)
        self._name_job = None;self._pending_name = None;self.rename_button.configure(state='normal')
        success = payload.get('type') == 'rename_client_success'
        if success and client:self.update_client_data(client)
        self.name_status_label.configure(text='Το όνομα αποθηκεύτηκε.' if success else 'Αποτυχία αλλαγής ονόματος. Το draft διατηρήθηκε.',
                                         text_color=COLORS.success if success else COLORS.danger)

    def _reset_client_token(self):
        """Διατηρεί την υπάρχουσα ρητή επιβεβαίωση χωρίς αλλαγή πρωτοκόλλου."""
        if self._reset_pending or not self._dashboard_online:return
        owner = self.winfo_toplevel();dialog = TokenResetDialog(owner);answer = dialog.get_input()
        owner.after_idle(owner.focus_force)
        if answer != 'RESET':
            self._set_security_status('Το reset ακυρώθηκε.');logger.info('Ακύρωση reset token Overview. client_code=%s',self.client_code);return
        try:
            if not self.on_reset_token_callback or self.on_reset_token_callback(self.client_code) is False:raise RuntimeError('not_sent')
            self._reset_pending = True;self.reset_token_button.configure(state='disabled')
            self._set_security_status('Στάλθηκε αίτημα. Αναμονή επιβεβαίωσης…',COLORS.info)
            self._reset_job = self.after(30000,self._reset_timeout)
            logger.warning('Αίτημα reset token Overview. client_code=%s',self.client_code)
        except Exception:
            self._set_security_status('Το αίτημα δεν στάλθηκε. Ελέγξτε τη σύνδεση Dashboard.',COLORS.danger)
            logger.warning('Αποτυχία αποστολής reset token Overview. client_code=%s',self.client_code)

    def _reset_timeout(self):
        """Επιτρέπει επανέλεγχο χωρίς να υπόσχεται αποτέλεσμα."""
        self._reset_job = None;self._reset_pending = False;self.reset_token_button.configure(state='normal')
        self._set_security_status('Δεν επιβεβαιώθηκε το reset. Ελέγξτε την κατάσταση Client πριν επαναλάβετε.',COLORS.warning)

    def handle_client_token_reset_result(self,payload):
        """Δεν εμφανίζει αποτέλεσμα άλλου Client ή τιμές token."""
        if payload.get('client_code') not in (None,self.client_code):return
        if self._reset_job:self.after_cancel(self._reset_job)
        self._reset_job = None;self._reset_pending = False;self.reset_token_button.configure(state='normal')
        success = payload.get('type') == 'client_token_reset_success'
        self._set_security_status('Το token μηδενίστηκε. Αναμονή επανασύνδεσης Client…' if success else 'Αποτυχία reset token. Ελέγξτε τη σύνδεση και τα δικαιώματα.',
                                  COLORS.success if success else COLORS.danger)

    def _set_security_status(self,message,color=COLORS.text_muted):
        """Εμφανίζει την κατάσταση στην ενότητα Security."""
        self.security_status_label.configure(text=message,text_color=color)

    def _bind_shortcuts(self):
        """Περιορίζει τις συντομεύσεις στα widgets της καρτέλας Overview."""
        owner = self.winfo_toplevel()
        for sequence,action in [('<Control-s>',self._save_name),('<Control-l>',self.rename_entry.focus_set),
                                ('<Control-Shift-C>',self.copy_details),('<Control-Shift-R>',self._reset_client_token)]:
            def handler(event,callback=action):
                focus = owner.focus_get()
                while focus is not None:
                    if focus is self:callback();return 'break'
                    focus = getattr(focus,'master',None)
            self._bindings.append((sequence,owner.bind(sequence,handler,add='+')))

    def destroy(self):
        """Καθαρίζει callbacks και δεσμεύσεις μόνο αυτής της καρτέλας."""
        for job in (self._name_job,self._reset_job,self._layout_job):
            if job:self.after_cancel(job)
        owner = self.winfo_toplevel()
        for sequence,binding in self._bindings:owner.unbind(sequence,binding)
        super().destroy()
