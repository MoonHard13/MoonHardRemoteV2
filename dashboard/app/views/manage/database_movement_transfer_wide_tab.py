from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS
from app.views.manage.database_movement_transfer_documents_tab import MovementTransferDocumentsTab


class MovementTransferWideDocumentsTab(MovementTransferDocumentsTab):
    """Keeps the normal Database columns and makes only Movement Transfer full width."""

    def _card(self, parent, title: str, description: str, warning: bool = False):
        # All existing Database cards keep their original parent/column.
        # Only Movement Transfer is created directly in the operations grid so
        # it can span both columns without changing left_stack/right_stack.
        if title == "Μεταφορά κινήσεων" and hasattr(self, "operations"):
            parent = self.operations
        return super()._card(parent, title, description, warning)

    def _build_ui(self) -> None:
        super()._build_ui()
        # The document list now has one extra visible column for NoteTypeDescr.
        self.document_results.grid_columnconfigure(7, weight=1)
        # DatabaseTab performs an early layout pass before the movement card
        # exists, so run one final pass after the extended UI is complete.
        self._apply_layout()

    def _apply_layout(self) -> None:
        # Preserve DatabaseTab's original layout for every existing feature:
        # left_stack and right_stack remain exactly as before.
        super()._apply_layout()

        if not hasattr(self, "movement_card"):
            return

        # Movement Transfer is the only card that spans both operation columns.
        # Row 2 is already used by the shortcuts hint, so place it underneath.
        self.movement_card.grid_configure(
            row=3,
            column=0,
            columnspan=2,
            padx=4,
            pady=(4, 10),
            sticky="ew",
        )

    def _apply_receipts(self, receipts: list[dict]) -> None:
        self._clear_document_results()
        if not receipts:
            self._show_document_message("Δεν βρέθηκαν παραστατικά.")
            return

        headers = (
            "",
            "Περιγραφή παραστατικού",
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
                str(document.get("document_descr") or ""),
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

    def _show_document_message(self, message: str) -> None:
        if not hasattr(self, "document_results"):
            return
        ctk.CTkLabel(
            self.document_results,
            text=message,
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=0, column=0, columnspan=8, padx=8, pady=10, sticky="ew")

    def _format_result(self, payload: dict) -> str:
        if payload.get("action") == "movement_receipt_search":
            documents = payload.get("receipts") or []
            lines = [
                "Action: Αναζήτηση παραστατικών",
                f"Results: {len(documents)}",
            ]
            for document in documents[:20]:
                lines.append(
                    f"- {document.get('document_descr') or '-'} | "
                    f"No {document.get('note_no')} | Code {document.get('note_code')} | "
                    f"Εστιατορική {document.get('init_date')} | "
                    f"Πραγματική {document.get('real_date')} | "
                    f"Station {document.get('station_oid')}"
                )
            return "\n".join(lines)
        return super()._format_result(payload)
