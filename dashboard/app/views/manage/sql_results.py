"""Πίνακες και μηνύματα SSMS με επιλογή result set και εξαγωγή."""

import logging
from tkinter import filedialog
from pathlib import Path

import customtkinter as ctk
from tksheet import Sheet

from app.sql_workspace import SqlResultData
from app.ui.theme import COLORS, FONTS, secondary_button_style

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
        """Πλέγμα κελιών με σταθερές επικεφαλίδες, αριθμούς και σχεδίαση μόνο ορατών κελιών."""
        frame = ctk.CTkFrame(self.body, fg_color=COLORS.background, corner_radius=0)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        columns = dataset.get('columns') or []
        rows = dataset.get('rows') or []
        sheet = Sheet(frame, headers=[str(value) for value in columns],
            data=[[SqlResultData.cell(value) for value in row] for row in rows],
            theme='dark', startup_focus=False, font=('Consolas', 11, 'normal'),
            header_font=('Segoe UI', 11, 'bold'), index_font=('Segoe UI', 10, 'normal'),
            default_row_height=28, default_header_height=30, default_row_index_width=56,
            show_horizontal_grid=True, show_vertical_grid=True, rounded_boxes=False,
            table_bg=COLORS.background, table_fg=COLORS.text_primary,
            table_grid_fg=COLORS.border_soft, header_bg=COLORS.surface_light,
            header_fg=COLORS.text_primary, index_bg=COLORS.surface_light,
            index_fg=COLORS.text_secondary, top_left_bg=COLORS.surface_light,
            table_selected_cells_border_fg=COLORS.accent,
            table_selected_cells_bg=COLORS.surface_light,
            table_selected_cells_fg=COLORS.text_primary)
        sheet.grid(row=0, column=0, sticky='nsew')
        # Μόνο επιλογή και αλλαγή διαστάσεων: ποτέ edit, paste, delete ή reorder.
        sheet.enable_bindings('single_select', 'drag_select', 'row_select', 'column_select',
            'column_width_resize', 'row_height_resize', 'double_click_column_resize',
            'arrowkeys', 'select_all', 'rc_select', 'right_click_popup_menu')
        widths = []
        for index, label in enumerate(columns):
            samples = [len(str(label)), *[len(SqlResultData.cell(row[index])[:50]) for row in rows[:40] if index < len(row)]]
            widths.append(max(110, min(360, max(samples) * 7 + 28)))
        sheet.set_column_widths(widths)
        sheet.bind('<Control-c>', lambda event: self.copy_selected())
        sheet.popup_menu_add_command('Copy selected cells', self.copy_selected)
        sheet.popup_menu_add_command('Copy all with headers', self.copy_all)
        sheet.popup_menu_add_command('Export CSV', self.export_csv)
        self.tables[name] = (frame, sheet)

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
        """Αντιγράφει τα επιλεγμένα ορθογώνια κελιών ως TSV χωρίς επικεφαλίδες."""
        name = self.selector.get()
        if name not in self.tables:
            return 'break'
        sheet = self.tables[name][1]
        item = self.datasets[name]
        blocks = []
        for r1, c1, r2, c2 in sheet.get_all_selection_boxes():
            rows = [row[c1:c2] for row in item['rows'][r1:r2]]
            blocks.append(SqlResultData.delimited([], rows, headers=False))
        if blocks:
            self._clipboard('\n'.join(blocks))
            logger.info('Αντιγραφή SQL κελιών. blocks=%s', len(blocks))
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
