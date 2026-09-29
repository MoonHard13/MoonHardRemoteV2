from __future__ import annotations

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
