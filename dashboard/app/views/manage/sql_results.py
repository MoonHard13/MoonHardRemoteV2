"""Πίνακες και μηνύματα SSMS με επιλογή result set και εξαγωγή."""

import logging
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path

import customtkinter as ctk

from app.sql_workspace import SqlResultData
from app.ui.theme import COLORS, FONTS, secondary_button_style, apply_treeview_style

logger = logging.getLogger(__name__)


class SqlResults(ctk.CTkFrame):
    """Διατηρεί πλήρες το επιστρεφόμενο μοντέλο ακόμη όσο ο πίνακας γεμίζει σταδιακά."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=COLORS.surface, corner_radius=8,
                         border_width=1, border_color=COLORS.border_soft)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.tables = {}
        self.datasets = {}
        self._jobs = []
        self._generation = 0
        self._menu = tk.Menu(self, tearoff=False)
        self._menu.add_command(label='Copy selected', command=self.copy_selected)
        self._menu.add_command(label='Copy all', command=self.copy_all)
        self._menu.add_command(label='Export CSV', command=self.export_csv)
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, padx=12, pady=(10, 4), sticky='ew')
        bar.grid_columnconfigure(0, weight=1)
        self.selector = ctk.CTkOptionMenu(bar, values=['Messages'], command=self.show,
                                         width=250, dynamic_resizing=False, fg_color=COLORS.surface_light,
                                         button_color=COLORS.accent, button_hover_color=COLORS.accent_hover)
        self.selector.grid(row=0, column=0, padx=(0, 12), sticky='ew')
        self.selector.bind('<Up>', lambda event: self.cycle(-1))
        self.selector.bind('<Down>', lambda event: self.cycle(1))
        self.copy_selected_button = ctk.CTkButton(bar, text='Copy selected', width=115, height=30,
                                                 command=self.copy_selected, **secondary_button_style())
        self.copy_selected_button.grid(row=0, column=1, padx=(0, 6))
        self.copy_all_button = ctk.CTkButton(bar, text='Copy all', width=90, height=30,
                                            command=self.copy_all, **secondary_button_style())
        self.copy_all_button.grid(row=0, column=2, padx=(0, 6))
        self.export_button = ctk.CTkButton(bar, text='Export CSV', width=100, height=30,
                                          command=self.export_csv, **secondary_button_style())
        self.export_button.grid(row=0, column=3)
        self.caption = ctk.CTkLabel(self, text='Αποτελέσματα και μηνύματα εκτέλεσης', height=22,
                                    font=FONTS.small, text_color=COLORS.text_secondary, anchor='w')
        self.caption.grid(row=1, column=0, padx=14, sticky='ew')
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.grid(row=2, column=0, padx=10, pady=(4, 10), sticky='nsew')
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)
        self.messages_box = ctk.CTkTextbox(self.body, font=FONTS.mono_body, wrap='word',
                                          fg_color=COLORS.background, text_color=COLORS.text_primary)
        self.messages_box.grid(sticky='nsew')
        self.set_messages('Γράψτε SQL και πατήστε F5. Τα αποτελέσματα θα εμφανιστούν εδώ.')
        self.show('Messages')

    def set_messages(self, text: str, append: bool = False):
        """Διατηρεί τα μηνύματα μόνο για ανάγνωση."""
        self.messages_box.configure(state='normal')
        if not append:
            self.messages_box.delete('1.0', 'end')
        self.messages_box.insert('end', ('\n' if append else '') + text)
        self.messages_box.configure(state='disabled')

    def clear(self):
        """Ακυρώνει την εκκρεμή εισαγωγή γραμμών πριν αλλάξει το αποτέλεσμα."""
        self._generation += 1
        for job in self._jobs:
            self.after_cancel(job)
        self._jobs.clear()
        for frame, tree in self.tables.values():
            frame.destroy()
        self.tables.clear()
        self.datasets.clear()
        self.selector.configure(values=['Messages'])
        self.selector.set('Messages')
        self.set_messages('')
        self.show('Messages')

    def render(self, payload: dict):
        """Παρουσιάζει κάθε επιστρεφόμενο result set με αριθμημένες επιλογές."""
        self.clear()
        self.set_messages(SqlResultData.messages(payload))
        for index, dataset in enumerate(SqlResultData.sets(payload), 1):
            name = f"Result {index} · Batch {dataset['batch_index']}"
            self.datasets[name] = dataset
            self._add_table(name, dataset)
        self.selector.configure(values=['Messages', *self.datasets])
        selected = next(iter(self.datasets), 'Messages') if not SqlResultData.failed(payload) else 'Messages'
        self.selector.set(selected)
        self.show(selected)

    def _add_table(self, name: str, dataset: dict):
        """Χρησιμοποιεί μοναδικά column IDs ακόμη όταν το SQL επιστρέφει διπλά ονόματα."""
        frame = ctk.CTkFrame(self.body, fg_color=COLORS.background, corner_radius=0)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        columns = dataset.get('columns') or []
        ids = [f'column_{index}' for index in range(len(columns))]
        tree = ttk.Treeview(frame, columns=ids, show='headings', selectmode='extended',
                            style=apply_treeview_style('MoonHard.SqlResult.Treeview'))
        tree.grid(row=0, column=0, sticky='nsew')
        vertical = ctk.CTkScrollbar(frame, orientation='vertical', command=tree.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ctk.CTkScrollbar(frame, orientation='horizontal', command=tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        rows = dataset.get('rows') or []
        for index, (column_id, label) in enumerate(zip(ids, columns)):
            samples = [len(str(label)), *[len(SqlResultData.cell(row[index])[:50]) for row in rows[:40] if index < len(row)]]
            tree.heading(column_id, text=str(label))
            tree.column(column_id, width=max(110, min(360, max(samples) * 7 + 28)), minwidth=70, stretch=False)
        self.tables[name] = (frame, tree)
        generation = self._generation
        def insert(start=0):
            """Εισάγει μικρές ομάδες γραμμών ώστε να μην παγώνει η οθόνη."""
            if generation != self._generation:
                return
            for index in range(start, min(start + 100, len(rows))):
                tree.insert('', 'end', iid=str(index), values=[SqlResultData.cell(value) for value in rows[index]])
            if start + 100 < len(rows):
                job = self.after_idle(lambda: insert(start + 100))
                self._jobs.append(job)
        insert()
        tree.bind('<Control-c>', lambda event: self.copy_selected())
        tree.bind('<Control-a>', lambda event, t=tree: self._select_all(t))
        tree.bind('<Button-3>', lambda event, t=tree: self._context_menu(event, t))

    def show(self, name: str):
        """Εναλλάσσει πίνακα/μηνύματα και ενημερώνει πλήθος και όρια αποτελεσμάτων."""
        self.messages_box.grid_remove()
        for frame, tree in self.tables.values():
            frame.grid_remove()
        table = name in self.tables
        if table:
            self.tables[name][0].grid(row=0, column=0, sticky='nsew')
            item = self.datasets[name]
            caption = f"{len(item.get('rows') or [])} γραμμές · {len(item.get('columns') or [])} στήλες"
            if item.get('limited'):
                caption += ' · Περιορισμένα αποτελέσματα από τον Client'
            self.caption.configure(text=caption, text_color=COLORS.warning if item.get('limited') else COLORS.text_secondary)
        else:
            self.messages_box.grid()
            self.caption.configure(text='Μηνύματα εκτέλεσης', text_color=COLORS.text_secondary)
        self.copy_selected_button.configure(state='normal' if table else 'disabled')
        self.copy_all_button.configure(state='normal')
        self.export_button.configure(state='normal' if table else 'disabled')

    def copy_selected(self):
        """Αντιγράφει τις επιλεγμένες γραμμές με επικεφαλίδες ως TSV."""
        name = self.selector.get()
        if name not in self.tables:
            return 'break'
        selected = self.tables[name][1].selection()
        item = self.datasets[name]
        if selected:
            rows = [item['rows'][int(index)] for index in selected]
            self._clipboard(SqlResultData.delimited(item['columns'], rows))
            logger.info('Αντιγραφή επιλεγμένων SQL γραμμών. rows=%s', len(rows))
        return 'break'

    def cycle(self, step: int):
        """Επιλέγει αποτέλεσμα από το πληκτρολόγιο χωρίς νέο SQL αίτημα."""
        values = ['Messages', *self.datasets]
        value = values[(values.index(self.selector.get()) + step) % len(values)]
        self.selector.set(value)
        self.show(value)
        return 'break'

    def show_messages(self):
        """Ανοίγει τα μηνύματα από συντόμευση."""
        self.selector.set('Messages')
        self.show('Messages')

    def copy_all(self):
        """Αντιγράφει το πλήρες επιστρεφόμενο result set ακόμη κατά την εμφάνιση γραμμών."""
        name = self.selector.get()
        if name in self.datasets:
            item = self.datasets[name]
            self._clipboard(SqlResultData.delimited(item['columns'], item.get('rows') or []))
        else:
            self._clipboard(self.messages_box.get('1.0', 'end-1c'))
        logger.info('Αντιγραφή SQL αποτελεσμάτων ή μηνυμάτων.')

    def _clipboard(self, value: str):
        """Ενημερώνει το clipboard χωρίς καταγραφή των δεδομένων."""
        self.clipboard_clear()
        self.clipboard_append(value)

    def export_csv(self):
        """Εξάγει μόνο τις γραμμές που έχουν επιστραφεί από τον Client σε UTF-8 με BOM."""
        item = self.datasets.get(self.selector.get())
        if not item:
            return
        owner = self.winfo_toplevel()
        path = filedialog.asksaveasfilename(parent=owner, title='Export SQL results',
                                          defaultextension='.csv', filetypes=[('CSV', '*.csv')])
        owner.after_idle(owner.focus_force)
        if path:
            try:
                Path(path).write_text(SqlResultData.delimited(item['columns'], item.get('rows') or [], ','),
                                      encoding='utf-8-sig', newline='')
                logger.info('Εξαγωγή SQL result set σε CSV. rows=%s', len(item.get('rows') or []))
            except OSError:
                self.set_messages('Αποτυχία αποθήκευσης CSV. Ελέγξτε τη διαδρομή και τα δικαιώματα.', append=True)
                self.show_messages()
                logger.error('Αποτυχία εξαγωγής SQL CSV.')

    @staticmethod
    def _select_all(tree):
        """Επιλέγει όλες τις ήδη εμφανισμένες γραμμές."""
        tree.selection_set(tree.get_children())
        return 'break'

    def _context_menu(self, event, tree):
        """Επιλέγει τη γραμμή δεξιού κλικ χωρίς να χάνει υπάρχουσα πολλαπλή επιλογή."""
        row = tree.identify_row(event.y)
        if row and row not in tree.selection():
            tree.selection_set(row)
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def destroy(self):
        """Ακυρώνει την εκκρεμή εισαγωγή γραμμών πριν κλείσει το παράθυρο."""
        for job in self._jobs:
            self.after_cancel(job)
        self._jobs.clear()
        super().destroy()
