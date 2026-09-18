"""SQL editor με αριθμούς γραμμών και ελαφρύ χρωματισμό σύνταξης."""

import re
import tkinter as tk
import customtkinter as ctk
from app.ui.theme import COLORS, FONTS


class SqlEditor(ctk.CTkFrame):
    """Συμπληρώνει το πραγματικό CustomTkinter textbox χωρίς πρόσθετες βιβλιοθήκες."""

    TOKEN = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|TOP|AS|AND|OR|NOT|NULL|IS|INSERT|INTO|VALUES|UPDATE|SET|DELETE|EXEC|EXECUTE|GO|DECLARE|BEGIN|END|CREATE|ALTER|DROP|DISTINCT|UNION|ALL|CASE|WHEN|THEN|ELSE)\b", re.I | re.S)

    def __init__(self, parent):
        super().__init__(parent, fg_color=COLORS.background, corner_radius=8,
                         border_width=1, border_color=COLORS.border_soft)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._paint_job = None
        self._highlight_job = None
        self.gutter = tk.Canvas(self, width=48, bg=COLORS.background, highlightthickness=0)
        self.gutter.grid(row=0, column=0, padx=(5, 0), pady=5, sticky='ns')
        self.box = ctk.CTkTextbox(self, font=FONTS.mono_body, wrap='none',
                                  fg_color=COLORS.background, text_color=COLORS.text_primary,
                                  border_width=0, undo=True)
        self.box.grid(row=0, column=1, padx=(0, 5), pady=5, sticky='nsew')
        self.cursor_label = ctk.CTkLabel(self, text='Ln 1 · Col 1', font=FONTS.small,
                                        text_color=COLORS.text_muted, anchor='w', height=22)
        self.cursor_label.grid(row=1, column=0, columnspan=2, padx=12, sticky='ew')
        text = self.box._textbox
        for name, color in (('keyword', COLORS.info), ('comment', COLORS.text_muted), ('string', COLORS.success)):
            text.tag_configure(name, foreground=color)
        text.configure(yscrollcommand=self._scroll)
        text.bind('<<Modified>>', self._modified, add='+')
        text.bind('<KeyRelease>', self._schedule_paint, add='+')
        text.bind('<ButtonRelease-1>', self._schedule_paint, add='+')
        text.bind('<Configure>', self._schedule_paint, add='+')
        self.box.insert('1.0', 'SELECT TOP 10 *\nFROM INFORMATION_SCHEMA.TABLES;')

    def _scroll(self, first, last):
        """Συγχρονίζει κύλιση editor και ορατούς αριθμούς γραμμών."""
        self.box._y_scrollbar.set(first, last)
        self._schedule_paint()

    def _modified(self, event=None):
        """Χρωματίζει μόνο μετά από αλλαγή περιεχομένου με μικρή καθυστέρηση."""
        text = self.box._textbox
        if not text.edit_modified():
            return
        text.edit_modified(False)
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(180, self.highlight)
        self._schedule_paint()

    def highlight(self):
        """Περιορίζει τον χρωματισμό στο πρώτο τμήμα μεγάλων scripts χωρίς περιορισμό εκτέλεσης."""
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = None
        text = self.box._textbox
        for tag in ('keyword', 'comment', 'string'):
            text.tag_remove(tag, '1.0', 'end')
        value = text.get('1.0', '1.0+100000c')
        for match in self.TOKEN.finditer(value):
            token = match.group()
            tag = 'comment' if token.startswith(('--', '/*')) else 'string' if token.startswith("'") else 'keyword'
            text.tag_add(tag, f'1.0+{match.start()}c', f'1.0+{match.end()}c')

    def _schedule_paint(self, event=None):
        """Συγχωνεύει redraw από κύλιση, κλικ και πληκτρολόγηση."""
        if self._paint_job is None:
            self._paint_job = self.after_idle(self._paint)

    def _paint(self):
        """Ζωγραφίζει μόνο τις ορατές γραμμές και εμφανίζει θέση/επιλογή."""
        self._paint_job = None
        self.gutter.delete('all')
        text = self.box._textbox
        index = text.index('@0,0')
        for _ in range(200):
            line = text.dlineinfo(index)
            if line is None:
                break
            self.gutter.create_text(39, line[1] + line[3] / 2, anchor='e', text=index.split('.')[0],
                                     font=text.cget('font'), fill=COLORS.text_muted)
            index = text.index(f'{index}+1line')
        row, column = text.index('insert').split('.')
        selected = bool(text.tag_ranges('sel'))
        self.cursor_label.configure(text=f'Ln {row} · Col {int(column)+1}' +
                                    ('  ·  F5: εκτέλεση επιλογής' if selected else '  ·  F5: εκτέλεση script'))

    def selected_or_all(self) -> str:
        """Επιστρέφει την επιλογή όταν υπάρχει, διαφορετικά ολόκληρο το script."""
        text = self.box._textbox
        return text.get('sel.first', 'sel.last').strip() if text.tag_ranges('sel') else self.box.get('1.0', 'end-1c').strip()

    def destroy(self):
        """Ακυρώνει τα δικά του callbacks πριν καταστραφεί το widget."""
        for job in (self._paint_job, self._highlight_job):
            if job:
                self.after_cancel(job)
        self._paint_job = self._highlight_job = None
        super().destroy()
