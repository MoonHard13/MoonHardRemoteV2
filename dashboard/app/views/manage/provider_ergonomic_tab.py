from __future__ import annotations

"""Ergonomic Provider layout while preserving all existing Provider behavior."""

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    primary_button_style,
    secondary_button_style,
)
from app.views.manage.provider_tab import ProviderTab


class ErgonomicProviderTab(ProviderTab):
    """Provider UI variant focused on a larger results workspace.

    All networking, filtering and Provider actions remain implemented by
    ``ProviderTab``. This subclass changes layout only.
    """

    ACTION_ORDER = (
        "send_selected",
        "send_all",
        "errors",
        "payways",
        "delete_mydata",
    )

    def _build_ui(self) -> None:
        super()._build_ui()

        # The invoice result table is the primary workspace. Keep surrounding
        # cards compact and let row 2 consume all remaining vertical space.
        self.main_content.grid_rowconfigure(2, weight=1)
        self.provider_header.grid_configure(pady=(SPACING.card_padding, 8))
        self.search_card.grid_configure(pady=(0, 8))
        self.provider_table_card.grid_configure(
            pady=(0, SPACING.card_padding),
            sticky="nsew",
        )

        # A larger requested row count makes the table visibly dominant when
        # the Manage window is maximized, while grid still shrinks it safely.
        self.provider_tree.configure(height=22)

    def _build_actions(self) -> None:
        """Place every Provider action on one compact row under the results."""

        # Integrate the action/status area into the results card instead of
        # using a separate bottom card. This removes a card gap and gives the
        # results section a substantially larger visual/usable frame.
        self.provider_actions_card = self.provider_table_card
        self.provider_action_frame = ctk.CTkFrame(
            self.provider_table_card,
            fg_color="transparent",
        )
        self.provider_action_frame.grid(
            row=4,
            column=0,
            columnspan=2,
            padx=12,
            pady=(7, 5),
            sticky="ew",
        )
        actions_frame = self.provider_action_frame
        actions_frame.grid_columnconfigure(5, weight=1)

        self.send_selected_button = ctk.CTkButton(
            actions_frame,
            text="Send selected",
            width=188,
            height=32,
            command=self._send_selected,
            **primary_button_style(),
        )
        self.send_selected_button.grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.send_all_button = ctk.CTkButton(
            actions_frame,
            text="Send all",
            width=190,
            height=32,
            command=self._send_all,
            **primary_button_style(),
        )
        self.send_all_button.grid(row=0, column=1, padx=5, sticky="w")

        self.errors_button = ctk.CTkButton(
            actions_frame,
            text="Errors",
            width=112,
            height=32,
            command=self._show_errors,
            **secondary_button_style(),
        )
        self.errors_button.grid(row=0, column=2, padx=5, sticky="w")

        self.payways_button = ctk.CTkButton(
            actions_frame,
            text="Payways",
            width=122,
            height=32,
            command=self._show_payways,
            **secondary_button_style(),
        )
        self.payways_button.grid(row=0, column=3, padx=5, sticky="w")

        self.mydata_button = ctk.CTkButton(
            actions_frame,
            text="Delete MyDATA",
            width=188,
            height=32,
            command=self._delete_mydata,
            fg_color=COLORS.danger_soft,
            hover_color=COLORS.danger,
            text_color=COLORS.danger,
            border_width=1,
            border_color=COLORS.danger,
            corner_radius=SPACING.button_radius,
            font=FONTS.body_bold,
        )
        self.mydata_button.grid(row=0, column=4, padx=(5, 0), sticky="w")

        self.provider_status_label = ctk.CTkLabel(
            self.provider_table_card,
            text="Ready",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=24,
            anchor="w",
        )
        self.provider_status_label.grid(
            row=5,
            column=0,
            columnspan=2,
            padx=12,
            pady=(0, 9),
            sticky="ew",
        )

        self.provider_action_buttons = [
            self.send_selected_button,
            self.send_all_button,
            self.errors_button,
            self.payways_button,
            self.mydata_button,
        ]

    def _apply_layout(self) -> None:
        """Keep filters responsive but never wrap the bottom action buttons."""

        self._layout_job = None
        try:
            wide = self.winfo_width() >= 1180
        except Exception:
            return

        # Filter layout still adapts to the available width.
        if wide != self._wide_layout:
            self._wide_layout = wide
            for frame in self.provider_filter_frames:
                frame.grid_forget()
            for column in range(4):
                self.provider_filters.grid_columnconfigure(
                    column,
                    weight=0,
                    uniform="",
                )

            columns = 4 if wide else 2
            for column in range(columns):
                self.provider_filters.grid_columnconfigure(
                    column,
                    weight=1,
                    uniform="provider-filter",
                )
            for index, frame in enumerate(self.provider_filter_frames):
                frame.grid(
                    row=index // columns,
                    column=index % columns,
                    padx=8,
                    pady=(0, 7),
                    sticky="ew",
                )

        # Explicitly enforce a single action row on every resize. This also
        # recovers cleanly if an older layout had already wrapped the buttons.
        for button in self.provider_action_buttons:
            button.grid_forget()
        for column, button in enumerate(self.provider_action_buttons):
            button.grid(
                row=0,
                column=column,
                padx=(0 if column == 0 else 5, 0 if column == 4 else 5),
                pady=0,
                sticky="w",
            )
