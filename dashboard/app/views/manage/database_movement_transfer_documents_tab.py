from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, secondary_button_style
from app.views.manage.database_movement_transfer_tab import MovementTransferDatabaseTab


class MovementTransferDocumentsTab(MovementTransferDatabaseTab):
    """Document-oriented movement transfer UI with date listing and multi-select."""

    RECEIPT_MODE = "Παραστατικό"
    ACTION_TITLES = {
        **MovementTransferDatabaseTab.ACTION_TITLES,
        "movement_receipt_search": "Αναζήτηση παραστατικών",
        "movement_transfer_receipt": "Μεταφορά παραστατικού",
    }

    def _build_ui(self) -> None:
        super()._build_ui()

        self._document_vars: dict[str, tk.BooleanVar] = {}
        self._document_rows: dict[str, dict] = {}
        self._document_transfer_queue: list[dict] = []
        self._document_transfer_current: dict | None = None
        self._document_transfer_total = 0
        self._document_transfer_completed = 0
        self._document_batch_active = False

        self._polish_document_terms(self.movement_card)
        self.receipt_search_button.configure(text="Αναζήτηση παραστατικών")
        self.receipt_transfer_button.configure(text="Μεταφορά επιλεγμένων παραστατικών")

        self.receipt_option.grid_remove()
        self.receipt_new_entry.master.grid_configure(row=5)
        self.receipt_transfer_button.grid_configure(row=5)

        toolbar = ctk.CTkFrame(self.receipt_frame, fg_color="transparent")
        toolbar.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="ew")
        toolbar.grid_columnconfigure(2, weight=1)

        self.select_all_documents_button = ctk.CTkButton(
            toolbar,
            text="Επιλογή όλων",
            width=112,
            height=30,
            command=self._select_all_documents,
            **secondary_button_style(),
        )
        self.select_all_documents_button.grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.action_buttons.append(self.select_all_documents_button)

        self.clear_documents_button = ctk.CTkButton(
            toolbar,
            text="Καθαρισμός",
            width=100,
            height=30,
            command=self._clear_document_selection,
            **secondary_button_style(),
        )
        self.clear_documents_button.grid(row=0, column=1, sticky="w")
        self.action_buttons.append(self.clear_documents_button)

        self.selected_documents_label = ctk.CTkLabel(
            toolbar,
            text="Επιλεγμένα: 0",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
        )
        self.selected_documents_label.grid(row=0, column=2, padx=(12, 0), sticky="e")

        self.document_results = ctk.CTkScrollableFrame(
            self.receipt_frame,
            height=210,
            fg_color=COLORS.background,
            border_color=COLORS.border,
            border_width=1,
        )
        self.document_results.grid(
            row=4,
            column=0,
            columnspan=2,
            padx=16,
            pady=(0, 10),
            sticky="ew",
        )
        for column, weight in enumerate((0, 1, 1, 1, 1, 2, 1)):
            self.document_results.grid_columnconfigure(column, weight=weight)

        self._show_document_message(
            "Βάλε αριθμό παραστατικού ή εστιατορική ημερομηνία και πάτησε Αναζήτηση."
        )

    def _polish_document_terms(self, widget) -> None:
        replacements = (
            ("Απόδειξης", "Παραστατικού"),
            ("απόδειξης", "παραστατικού"),
            ("Απόδειξη", "Παραστατικό"),
            ("απόδειξη", "παραστατικό"),
        )
        for child in widget.winfo_children():
            try:
                text = child.cget("text")
            except Exception:
                text = None
            if isinstance(text, str) and text:
                new_text = text
                for old, new in replacements:
                    new_text = new_text.replace(old, new)
                if new_text == "Ημερομηνία (προαιρετική) · YYYYMMDD":
                    new_text = "Εστιατορική ημερομηνία · YYYYMMDD"
                if new_text != text:
                    child.configure(text=new_text)
            self._polish_document_terms(child)

    def request_receipt_search(self) -> None:
        note_no = self.receipt_no_entry.get().strip()
        search_date = self.receipt_date_entry.get().strip()

        if not note_no and not search_date:
            self._set_status(
                "Βάλε αριθμό παραστατικού ή εστιατορική ημερομηνία.",
                COLORS.danger,
            )
            return
        if note_no and not note_no.isdigit():
            self._set_status("Ο αριθμός παραστατικού πρέπει να είναι αριθμητικός.", COLORS.danger)
            return
        if search_date and not self._valid_date(search_date):
            self._set_status("Η εστιατορική ημερομηνία πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return

        station_oid = self._selected_station_oid()
        if station_oid is None:
            return

        self._clear_document_results()
        self._show_document_message("Αναζήτηση παραστατικών...")
        self.request_action(
            "movement_receipt_search",
            {
                "note_no": note_no,
                "search_date": search_date,
                "station_oid": station_oid,
            },
        )

    def _apply_receipts(self, receipts: list[dict]) -> None:
        self._clear_document_results()
        if not receipts:
            self._show_document_message("Δεν βρέθηκαν παραστατικά.")
            return

        headers = (
            "",
            "Αρ. παραστατικού",
            "Code",
            "Εστιατορική",
            "Πραγματική",
            "SalesStation",
            "Ποσό",
        )
        for column, title in enumerate(headers):
            ctk.CTkLabel(
                self.document_results,
                text=title,
                font=FONTS.small_bold if hasattr(FONTS, "small_bold") else FONTS.small,
                text_color=COLORS.text_secondary,
                anchor="w",
            ).grid(row=0, column=column, padx=5, pady=(2, 6), sticky="ew")

        for index, document in enumerate(receipts, start=1):
            key = self._document_key(document, index)
            variable = tk.BooleanVar(value=False)
            self._document_vars[key] = variable
            self._document_rows[key] = document

            checkbox = ctk.CTkCheckBox(
                self.document_results,
                text="",
                width=24,
                variable=variable,
                command=self._update_selected_count,
            )
            checkbox.grid(row=index, column=0, padx=5, pady=4, sticky="w")

            value = document.get("value")
            amount = "-" if value is None else f"{float(value):.2f}"
            station = str(document.get("station_descr") or "").strip()
            if not station:
                station = f"OID {document.get('station_oid')}"

            values = (
                str(document.get("note_no") or ""),
                str(document.get("note_code") or ""),
                str(document.get("init_date") or ""),
                str(document.get("real_date") or ""),
                station,
                amount,
            )
            for column, text in enumerate(values, start=1):
                ctk.CTkLabel(
                    self.document_results,
                    text=text,
                    font=FONTS.small,
                    text_color=COLORS.text_primary,
                    anchor="w",
                ).grid(row=index, column=column, padx=5, pady=4, sticky="ew")

        self._update_selected_count()

    def _document_key(self, document: dict, index: int) -> str:
        return "|".join(
            (
                str(document.get("source") or ""),
                str(document.get("pos_hdr") or ""),
                str(document.get("note_no") or ""),
                str(document.get("note_code") or ""),
                str(document.get("init_date") or ""),
                str(document.get("station_oid") or ""),
                str(index),
            )
        )

    def _clear_document_results(self) -> None:
        self._document_vars.clear()
        self._document_rows.clear()
        if hasattr(self, "document_results"):
            for child in self.document_results.winfo_children():
                child.destroy()
        self._update_selected_count()

    def _show_document_message(self, message: str) -> None:
        if not hasattr(self, "document_results"):
            return
        ctk.CTkLabel(
            self.document_results,
            text=message,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=0, column=0, columnspan=7, padx=8, pady=10, sticky="ew")

    def _select_all_documents(self) -> None:
        for variable in self._document_vars.values():
            variable.set(True)
        self._update_selected_count()

    def _clear_document_selection(self) -> None:
        for variable in self._document_vars.values():
            variable.set(False)
        self._update_selected_count()

    def _update_selected_count(self) -> None:
        if not hasattr(self, "selected_documents_label"):
            return
        count = sum(1 for variable in self._document_vars.values() if variable.get())
        self.selected_documents_label.configure(text=f"Επιλεγμένα: {count}")

    def _selected_documents(self) -> list[dict]:
        return [
            self._document_rows[key]
            for key, variable in self._document_vars.items()
            if variable.get() and key in self._document_rows
        ]

    def request_receipt_transfer(self) -> None:
        selected = self._selected_documents()
        if not selected:
            self._set_status("Επίλεξε τουλάχιστον ένα παραστατικό.", COLORS.danger)
            return

        new_date = self.receipt_new_entry.get().strip()
        if not self._valid_date(new_date):
            self._set_status("Η νέα εστιατορική ημερομηνία πρέπει να είναι YYYYMMDD.", COLORS.danger)
            return

        unchanged = [item for item in selected if str(item.get("init_date") or "") == new_date]
        if unchanged:
            self._set_status(
                f"{len(unchanged)} επιλεγμένα παραστατικά είναι ήδη στην ημερομηνία {new_date}.",
                COLORS.danger,
            )
            return

        if not self._confirm(
            "Επιβεβαίωση μεταφοράς παραστατικών",
            f"Επιλεγμένα παραστατικά: {len(selected)}\n"
            f"Νέα εστιατορική ημερομηνία: {new_date}\n\n"
            "Θα μεταφερθούν όλες οι γραμμές, οι πληρωμές και τα σχετικά transfers "
            "για κάθε επιλεγμένο παραστατικό. Συνέχεια;",
        ):
            return

        self._document_transfer_queue = list(selected)
        self._document_transfer_total = len(selected)
        self._document_transfer_completed = 0
        self._document_batch_active = True
        self._document_target_date = new_date
        self._start_next_document_transfer()

    def _start_next_document_transfer(self) -> None:
        if not self._document_transfer_queue:
            self._finish_document_batch()
            return

        document = self._document_transfer_queue.pop(0)
        self._document_transfer_current = document
        ordinal = self._document_transfer_completed + 1
        self._set_status(
            f"Μεταφορά παραστατικού {ordinal} από {self._document_transfer_total}...",
            COLORS.accent,
        )
        self.request_action(
            "movement_transfer_receipt",
            {
                "source": str(document["source"]),
                "pos_hdr": str(document["pos_hdr"]),
                "note_no": str(document["note_no"]),
                "note_code": str(document["note_code"]),
                "old_date": str(document["init_date"]),
                "new_date": self._document_target_date,
                "station_oid": str(document["station_oid"]),
            },
        )
        if self.current_action == "movement_transfer_receipt":
            self.progress_bar.set(0)
            self.progress_bar.grid()

    def handle_result(self, payload: dict) -> None:
        is_batch_result = (
            self._document_batch_active
            and payload.get("client_code") == self.client_code
            and payload.get("request_id") == self.current_request_id
            and payload.get("action") == "movement_transfer_receipt"
            and self.current_action == "movement_transfer_receipt"
        )
        success = bool(payload.get("success"))

        super().handle_result(payload)

        if not is_batch_result:
            return

        if not success:
            completed = self._document_transfer_completed
            self._document_transfer_queue.clear()
            self._document_batch_active = False
            self._document_transfer_current = None
            self._set_status(
                f"Η μεταφορά σταμάτησε μετά από {completed} επιτυχημένα παραστατικά.",
                COLORS.danger,
            )
            return

        self._document_transfer_completed += 1
        self._document_transfer_current = None
        if self._document_transfer_queue:
            self.after(50, self._start_next_document_transfer)
        else:
            self._finish_document_batch()

    def _finish_document_batch(self) -> None:
        if not self._document_batch_active:
            return
        completed = self._document_transfer_completed
        total = self._document_transfer_total
        self._document_batch_active = False
        self._document_transfer_current = None
        self._document_transfer_queue.clear()
        self.progress_bar.set(1)
        self._set_status(
            f"Μεταφέρθηκαν {completed} από {total} παραστατικά.",
            COLORS.success,
        )
        self._clear_document_results()
        self._show_document_message("Η μεταφορά ολοκληρώθηκε. Κάνε νέα αναζήτηση για ανανεωμένα αποτελέσματα.")

    def _on_bo_selected(self, selected_value: str) -> None:
        super()._on_bo_selected(selected_value)
        if hasattr(self, "document_results"):
            self._clear_document_results()
            self._show_document_message("Κάνε αναζήτηση παραστατικών στη νέα βάση.")

    def _format_result(self, payload: dict) -> str:
        action = payload.get("action")
        if action == "movement_receipt_search":
            documents = payload.get("receipts") or []
            lines = [
                "Action: Αναζήτηση παραστατικών",
                f"Results: {len(documents)}",
            ]
            for document in documents[:20]:
                lines.append(
                    f"- No {document.get('note_no')} | Code {document.get('note_code')} | "
                    f"Εστιατορική {document.get('init_date')} | "
                    f"Πραγματική {document.get('real_date')} | "
                    f"Station {document.get('station_oid')}"
                )
            return "\n".join(lines)
        return super()._format_result(payload)
