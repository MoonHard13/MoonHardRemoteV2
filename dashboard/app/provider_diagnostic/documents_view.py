"""Πίνακας και λεπτομέρειες πραγματικών παραστατικών μέσα στην ίδια καρτέλα."""

import json
import logging
import webbrowser
from datetime import date
from decimal import Decimal
from tkinter import filedialog, ttk

import customtkinter as ctk

from app.provider_diagnostic.documents import DocumentFields
from app.ui.theme import COLORS, FONTS, apply_treeview_style, secondary_button_style


logger = logging.getLogger(__name__)


class DocumentsView(ctk.CTkFrame):
    COLUMNS = (("dateIssued", "Ημερομηνία", 165), ("series", "Σειρά", 95),
               ("number", "Αριθμός", 95), ("invoiceType", "Τύπος", 80),
               ("counterPartyVAT", "ΑΦΜ αντισυμβαλλομένου", 165),
               ("totalAmount", "Συνολική αξία", 110), ("totalVatAmount", "ΦΠΑ", 105), ("mark", "MARK", 160))

    def __init__(self, parent, load, status):
        super().__init__(parent, fg_color="transparent")
        self.dataset = None
        self._rows = []
        self._render_job = self._filter_job = None
        self._sort_reverse = {}
        self._status = status
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        dates = ctk.CTkFrame(self, fg_color="transparent")
        dates.grid(row=0, column=0, sticky="ew", pady=4)
        self.date_from = ctk.CTkEntry(dates, width=120, placeholder_text="YYYYMMDD")
        self.date_to = ctk.CTkEntry(dates, width=120, placeholder_text="YYYYMMDD")
        today = date.today().strftime("%Y%m%d")
        for column, label, entry in ((0, "Από · Alt+1", self.date_from), (2, "Έως · Alt+2", self.date_to)):
            ctk.CTkLabel(dates, text=label).grid(row=0, column=column, padx=5)
            entry.grid(row=0, column=column + 1, padx=5)
            entry.insert(0, today)
            entry.bind("<Return>", lambda _: load())
        self.load_button = ctk.CTkButton(dates, text="Ανάκτηση · Ctrl+L", command=load,
            width=155, **secondary_button_style())
        self.load_button.grid(row=0, column=4, padx=8)
        self.scope = ctk.CTkLabel(dates, text="", anchor="w", wraplength=740, font=FONTS.small)
        self.scope.grid(row=1, column=0, columnspan=5, sticky="ew", padx=5, pady=4)
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", pady=4)
        self.filters = {}
        for column, (name, label) in enumerate((("series", "Σειρά"), ("number", "Αριθμός"),
                ("invoice_type", "Τύπος (ακριβής)"), ("mark", "MARK (ακριβές)"))):
            filters.grid_columnconfigure(column, weight=1)
            entry = ctk.CTkEntry(filters, placeholder_text=label, width=130)
            entry.grid(row=0, column=column, sticky="ew", padx=4)
            entry.bind("<KeyRelease>", self._schedule_filter)
            entry.bind("<Return>", lambda _: self.apply_filters())
            self.filters[name] = entry
        ctk.CTkButton(filters, text="Καθαρισμός · Ctrl+R", command=self.reset_filters,
            width=150, **secondary_button_style()).grid(row=0, column=4, padx=4)
        self.count = ctk.CTkLabel(self, text="Δεν έχουν ανακτηθεί παραστατικά.", anchor="w", font=FONTS.small)
        self.count.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        table = ctk.CTkFrame(self, fg_color="transparent")
        table.grid(row=3, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=[name for name, _, _ in self.COLUMNS],
            show="headings", selectmode="extended", style=apply_treeview_style())
        self.tree.grid(row=0, column=0, sticky="nsew")
        for name, label, width in self.COLUMNS:
            self.tree.heading(name, text=label, command=lambda key=name: self.sort(key))
            self.tree.column(name, width=width, minwidth=70, stretch=False)
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_details())
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=4)
        for column, (label, action) in enumerate((("Άνοιγμα URL · Ctrl+O", self.open_url),
                ("Αντιγραφή · Ctrl+C", self.copy_selected), ("Λεπτομέρειες · Ctrl+Shift+C", self.copy_details),
                ("Εξαγωγή JSON · Ctrl+E", self.export))):
            ctk.CTkButton(actions, text=label, command=action, width=170,
                **secondary_button_style()).grid(row=0, column=column, padx=3)
        self.details = ctk.CTkTextbox(self, height=150, wrap="word", font=FONTS.small)
        self.details.grid(row=5, column=0, sticky="ew", pady=4)
        self.details.configure(state="disabled")

    def _schedule_filter(self, event=None):
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
        self._filter_job = self.after(250, self.apply_filters)

    def set_dataset(self, dataset):
        self.dataset = dataset
        self.apply_filters()

    def clear(self):
        self.dataset = None
        for name in ("_render_job", "_filter_job"):
            job = getattr(self, name)
            if job is not None:
                self.after_cancel(job)
                setattr(self, name, None)
        self._rows = []
        self._render()
        self.count.configure(text="Δεν έχουν ανακτηθεί παραστατικά.")

    def apply_filters(self):
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
            self._filter_job = None
        values = {name: entry.get().strip() for name, entry in self.filters.items()}
        self._rows = self.dataset.filtered(**values) if self.dataset else []
        self._sort_reverse.clear()
        self._render()
        if self.dataset:
            self.count.configure(text=f"Ορατά: {len(self._rows)} / {len(self.dataset.records)} · "
                f"Διάστημα: {self.dataset.date_from}–{self.dataset.date_to} · "
                f"Σελίδες: {self.dataset.pages} · Ανάκτηση: {self.dataset.loaded_at}")
        logger.info("Φιλτράρισμα παραστατικών. visible=%s", len(self._rows))

    def reset_filters(self):
        for entry in self.filters.values():
            entry.delete(0, "end")
        self.apply_filters()

    def sort(self, name):
        reverse = self._sort_reverse.get(name, False)
        numeric = name in ("number", "totalAmount", "totalVatAmount", "mark")
        def key(row):
            value = DocumentFields.amount(row.get(name)) if numeric else str(row.get(name) or "").casefold()
            return (value is not None, value if value is not None else Decimal(0)) if numeric else value
        self._rows.sort(key=key, reverse=reverse)
        self._sort_reverse[name] = not reverse
        self._render()
        logger.info("Ταξινόμηση πίνακα παραστατικών. column=%s", name)

    def _render(self):
        if self._render_job is not None:
            self.after_cancel(self._render_job)
            self._render_job = None
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.show_details()
        # Εισαγωγή σε μικρές παρτίδες για να παραμένει διαθέσιμο το Tk event loop.
        def batch(position=0):
            self._render_job = None
            for index in range(position, min(position + 200, len(self._rows))):
                row = self._rows[index]
                self.tree.insert("", "end", iid=str(index), values=[
                    row.get(name) if row.get(name) is not None else "—" for name, _, _ in self.COLUMNS])
            if position + 200 < len(self._rows):
                self._render_job = self.after(10, lambda: batch(position + 200))
        batch()

    def selected(self):
        selected = self.tree.selection()
        return self._rows[int(selected[0])] if selected else None

    def show_details(self):
        row = self.selected()
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", json.dumps(row, ensure_ascii=False, indent=2) if row else
            "Επιλέξτε παραστατικό για λεπτομέρειες. Τα μη διαθέσιμα πεδία εμφανίζονται ως null.")
        self.details.configure(state="disabled")

    def open_url(self):
        row = self.selected()
        url = DocumentFields.safe_url(row.get("url")) if row else ""
        if not url:
            self._status("Δεν υπάρχει διαθέσιμο έγκυρο URL για το επιλεγμένο παραστατικό.")
            return
        try:
            if not webbrowser.open(url, new=2):
                self._status("Δεν ήταν δυνατό το άνοιγμα του browser.")
        except Exception:
            self._status("Δεν ήταν δυνατό το άνοιγμα του browser.")
        logger.info("Ζητήθηκε άνοιγμα URL παραστατικού.")

    def copy_selected(self):
        rows = [self._rows[int(iid)] for iid in self.tree.selection()]
        if rows:
            self.clipboard_clear()
            self.clipboard_append("\n".join("\t".join(str(row.get(name) or "") for name, _, _ in self.COLUMNS) for row in rows))
            logger.info("Αντιγραφή επιλεγμένων παραστατικών. records=%s", len(rows))

    def copy_details(self):
        row = self.selected()
        if row:
            self.clipboard_clear()
            self.clipboard_append(json.dumps(row, ensure_ascii=False, indent=2))
            logger.info("Αντιγραφή λεπτομερειών παραστατικού.")

    def export(self):
        if not self.dataset:
            self._status("Ανακτήστε πρώτα παραστατικά.")
            return
        path = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), defaultextension=".json",
            initialfile="provider-documents.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"date_from": self.dataset.date_from, "date_to": self.dataset.date_to,
                    "loaded_at": self.dataset.loaded_at, "records": self._rows}, stream, ensure_ascii=False, indent=2)
            self._status(f"Εξαγωγή ολοκληρώθηκε. Παραστατικά: {len(self._rows)}")
            logger.info("Εξαγωγή παραστατικών ολοκληρώθηκε. records=%s", len(self._rows))
        except OSError:
            self._status("Δεν ήταν δυνατή η αποθήκευση. Ελέγξτε δικαιώματα και διαθέσιμο χώρο.")
            logger.warning("Αποτυχία εξαγωγής παραστατικών.")

    def destroy(self):
        self.clear()
        super().destroy()
