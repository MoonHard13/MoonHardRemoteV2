from __future__ import annotations

from app.views.manage.database_movement_transfer_documents_tab import MovementTransferDocumentsTab


class MovementTransferWideDocumentsTab(MovementTransferDocumentsTab):
    """Uses both Database operation columns for the Movement Transfer feature."""

    def _apply_layout(self) -> None:
        super()._apply_layout()

        if not hasattr(self, "movement_card"):
            return

        operation_width = self.operations.winfo_width()
        if operation_width <= 100:
            available = max(self.winfo_width() - 48, 320)
            operation_width = available * 0.58 if self.winfo_width() >= 1550 else available
        paired_cards = operation_width >= 900

        # In wide mode the left stack becomes the two-column operation grid.
        # The existing right stack is placed inside its second column and the
        # Movement Transfer card spans both columns underneath both stacks.
        if paired_cards:
            self.right_stack.grid_forget()
            self.left_stack.grid_forget()

            self.left_stack.grid_columnconfigure(0, weight=3)
            self.left_stack.grid_columnconfigure(1, weight=2)
            self.left_stack.grid(
                row=0,
                column=0,
                columnspan=2,
                padx=4,
                sticky="new",
            )
            self.right_stack.grid(
                in_=self.left_stack,
                row=0,
                column=1,
                rowspan=3,
                padx=(14, 0),
                sticky="new",
            )
            self.movement_card.grid_configure(
                row=3,
                column=0,
                columnspan=2,
                padx=0,
                pady=(4, 10),
                sticky="ew",
            )
            return

        # Compact layout remains single-column so it still works on smaller
        # windows, while Movement Transfer takes the entire available width.
        self.right_stack.grid_forget()
        self.left_stack.grid_forget()
        self.left_stack.grid_columnconfigure(0, weight=1)
        self.left_stack.grid_columnconfigure(1, weight=0)
        self.left_stack.grid(
            row=0,
            column=0,
            columnspan=1,
            padx=4,
            sticky="new",
        )
        self.right_stack.grid(
            in_=self.operations,
            row=1,
            column=0,
            padx=4,
            sticky="new",
        )
        self.movement_card.grid_configure(
            row=3,
            column=0,
            columnspan=1,
            padx=0,
            pady=(0, 10),
            sticky="ew",
        )
