"""Πίνακας σύγκρισης με αυτόματη προβολή των δύο πηγών δεξιά."""

import customtkinter as ctk

from app.provider_diagnostic.documents_view import DocumentsView
from app.provider_diagnostic.reconciliation import STATUS_LABELS


class ReconciliationView(DocumentsView):
    EXPORT_FILENAME = "provider-reconciliation.json"
    COLUMNS = (("dateIssued", "Ημερομηνία", 160), ("series", "Σειρά", 90),
        ("number", "Αριθμός", 90), ("invoiceType", "Τύπος", 80),
        ("status_label", "Αποτέλεσμα", 260), ("mark", "MARK", 160),
        ("erp_amount", "Αξία ERP", 110), ("provider_amount", "Αξία Provider", 110),
        ("erp_vat", "ΦΠΑ ERP", 110), ("provider_vat", "ΦΠΑ Provider", 110))

    def __init__(self, parent, load, status):
        super().__init__(parent, load, status)
        self.load_button.configure(text="Σύγκριση · Ctrl+L")
        self.status_filter = ctk.CTkOptionMenu(self, values=["Όλα", *STATUS_LABELS.values()],
            command=lambda _: self.apply_filters(), width=280)
        self.status_filter.grid(row=5, column=0, sticky="w", padx=4, pady=4)

    def filter_values(self):
        values = super().filter_values()
        values["status"] = next((key for key, label in STATUS_LABELS.items()
            if label == self.status_filter.get()), "")
        return values

    def apply_filters(self):
        super().apply_filters()
        if self.dataset:
            summary = self.dataset.summary()
            counts = " · ".join(f"{STATUS_LABELS[key]}: {count}" for key, count in summary["statuses"].items())
            self.count.configure(text=f"Ορατά: {len(self._rows)} / {len(self.dataset.records)} · "
                f"ERP: {self.dataset.erp_records} · Provider: {self.dataset.provider_records} · "
                f"{self.dataset.date_from}–{self.dataset.date_to}\n{counts}\n"
                f"{self.dataset.warning or self.dataset.completion_note}\n"
                + "\n".join(self.dataset.erp_warnings))

    def reset_filters(self):
        self.status_filter.set("Όλα")
        super().reset_filters()
