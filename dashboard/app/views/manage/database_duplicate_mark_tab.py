from __future__ import annotations

from app.ui.theme import COLORS
from app.views.manage.database_tab import DatabaseTab


class DuplicateMarkDatabaseTab(DatabaseTab):
    """Προσθέτει την ελεγχόμενη διαγραφή διπλών ΜΑΡΚ στο Database tab."""

    ACTION_TITLES = {
        **DatabaseTab.ACTION_TITLES,
        "delete_duplicate_mark": "Διαγραφή διπλών ΜΑΡΚ",
    }

    def _build_ui(self) -> None:
        super()._build_ui()

        # Το MARK cleanup είναι ανεξάρτητη λειτουργική ενότητα και δεν
        # συγχέεται με τα γενικά Database maintenance actions.
        self.mark_cleanup_card = self._card(
            self.right_stack,
            "MARK cleanup",
            "Run the controlled duplicate MARK cleanup steps on the selected database.",
            warning=True,
        )
        self.mark_cleanup_card.grid(row=2, column=0, pady=(0, 10), sticky="ew")

        self.duplicate_mark_button = self._action_button(
            self.mark_cleanup_card,
            text="Διαγραφή διπλών ΜΑΡΚ",
            command=self.request_delete_duplicate_mark,
            style="danger",
        )
        self.duplicate_mark_button.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=16,
            pady=(0, 16),
            sticky="ew",
        )

    def request_delete_duplicate_mark(self) -> None:
        """Ζητά ρητή επιβεβαίωση πριν από το cleanup των διπλών ΜΑΡΚ."""

        if not self._confirm(
            "Επιβεβαίωση διαγραφής διπλών ΜΑΡΚ",
            "Θα εκτελεστούν διαδοχικά δύο ελεγχόμενα cleanup βήματα.\n\n"
            "1. Duplicate Success MARK cleanup (best effort).\n"
            "   Αν δεν υποστηρίζεται από το schema, θα εμφανιστεί warning και η διαδικασία θα συνεχίσει.\n"
            "2. Duplicate MARK cleanup (κύριο βήμα).\n\n"
            f"Database: {self.bo_option.get()}\n\n"
            "Η ενέργεια διαγράφει εγγραφές. Συνέχεια;",
        ):
            return

        self.request_action("delete_duplicate_mark")
        if self.current_action == "delete_duplicate_mark":
            self.progress_bar.set(0)
            self.progress_bar.grid()

    def handle_progress(self, payload: dict) -> None:
        """Εμφανίζει step-level progress για το duplicate MARK cleanup."""

        if payload.get("action") != "delete_duplicate_mark":
            super().handle_progress(payload)
            return
        if payload.get("client_code") != self.client_code:
            return
        if payload.get("request_id") != self.current_request_id:
            return
        if self.current_action != "delete_duplicate_mark":
            return

        message = str(payload.get("message") or "").strip()
        if not message:
            return

        percent = payload.get("percent")
        if type(percent) is int:
            self.progress_bar.set(max(0, min(percent, 100)) / 100)

        self._set_status(message, COLORS.accent)
        if message not in self._progress_messages:
            self._progress_messages.add(message)
            self._append_output(f"\n- {message}")

    def handle_result(self, payload: dict) -> None:
        """Κρατά warning status όταν μόνο το optional πρώτο βήμα απέτυχε."""

        is_current_duplicate = (
            payload.get("client_code") == self.client_code
            and payload.get("request_id") == self.current_request_id
            and payload.get("action") == "delete_duplicate_mark"
            and self.current_action == "delete_duplicate_mark"
        )
        super().handle_result(payload)

        if not is_current_duplicate or not payload.get("success"):
            return

        step_success = payload.get("success_step") or {}
        if step_success.get("success") is False:
            self._set_status(
                "Ολοκληρώθηκε με warning στο προαιρετικό Success cleanup.",
                COLORS.warning,
            )
        self.progress_bar.set(1)

    def _format_result(self, payload: dict) -> str:
        """Παρουσιάζει ανεξάρτητα τα δύο cleanup βήματα."""

        if payload.get("action") != "delete_duplicate_mark":
            return super()._format_result(payload)

        success_step = payload.get("success_step") or {}
        mark_step = payload.get("mark_step") or {}

        def step_lines(title: str, step: dict, optional: bool = False) -> list[str]:
            ok = bool(step.get("success"))
            status = "OK" if ok else ("WARNING" if optional else "FAILED")
            lines = [f"{title}: {status}"]
            if step.get("message"):
                lines.append(f"  {step.get('message')}")
            if step.get("deleted_rows") is not None:
                lines.append(f"  Deleted rows: {step.get('deleted_rows')}")
            if step.get("error"):
                lines.append(f"  Error: {step.get('error')}")
            return lines

        lines = [
            "Action: Διαγραφή διπλών ΜΑΡΚ",
            f"Database: {payload.get('database_name') or '-'}",
            f"Elapsed: {payload.get('elapsed_ms')} ms",
            "",
        ]
        lines.extend(step_lines("Step 1 - Duplicate Success MARK", success_step, optional=True))
        lines.append("")
        lines.extend(step_lines("Step 2 - Duplicate MARK", mark_step))
        lines.extend(
            (
                "",
                "Overall result: "
                + (
                    "Completed successfully."
                    if success_step.get("success") is not False
                    else "Completed with warning in optional Step 1."
                ),
            )
        )
        return "\n".join(lines)
