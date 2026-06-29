from typing import Callable

import customtkinter as ctk
from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    primary_button_style
)


class OverviewTab(ctk.CTkFrame):
    """
    Overview tab για βασικές πληροφορίες client και rename λειτουργία.
    """

    def __init__(
        self,
        parent,
        client: dict,
        on_rename_callback: Callable[[str, str], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Overview tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client = client
        self.on_rename_callback = on_rename_callback
        self.client_code = client.get("client_code", "")

        self.grid_columnconfigure(0, weight=1)

        self._build_ui()


    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του Overview tab.
        """

        frame = ctk.CTkFrame(self, **card_style())
        frame.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=SPACING.card_padding,
            sticky="ew"
        )
        frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            frame,
            text="Client Information",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 8), sticky="w")

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        app_version = self.client.get("app_version", "-")
        group_name = self.client.get("group_name") or "Ungrouped"
        last_seen = self.client.get("last_seen", "-")

        info_text = (
            f"Display name: {display_name}\n"
            f"PC name: {pc_name}\n"
            f"Username: {username}\n"
            f"Group: {group_name}\n"
            f"App version: {app_version}\n"
            f"Last seen: {last_seen}"
        )

        self.info_label = ctk.CTkLabel(
            frame,
            text=info_text,
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            justify="left",
            anchor="w"
        )
        self.info_label.grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 18), sticky="w")

        rename_title = ctk.CTkLabel(
            frame,
            text="Rename Client",
            font=FONTS.section_title,
            text_color=COLORS.text_primary
        )
        rename_title.grid(row=2, column=0, columnspan=2, padx=18, pady=(8, 8), sticky="w")

        self.rename_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Friendly name",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.rename_entry.grid(row=3, column=0, padx=(18, 10), pady=(0, 18), sticky="ew")
        self.rename_entry.insert(0, display_name)

        rename_button = ctk.CTkButton(
            frame,
            text="Save Name",
            width=120,
            command=self._save_name,
            **primary_button_style()
        )
        rename_button.grid(row=3, column=1, padx=(0, 18), pady=(0, 18), sticky="e")

    def update_client_data(self, client: dict) -> None:
        """
        Ενημερώνει τα στοιχεία του Overview tab όταν αλλάξει ο client.
        """

        if not client:
            return

        self.client = client

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        app_version = self.client.get("app_version", "-")
        group_name = self.client.get("group_name") or "Ungrouped"
        last_seen = self.client.get("last_seen", "-")

        info_text = (
            f"Display name: {display_name}\n"
            f"PC name: {pc_name}\n"
            f"Username: {username}\n"
            f"Group: {group_name}\n"
            f"App version: {app_version}\n"
            f"Last seen: {last_seen}"
        )

        if hasattr(self, "info_label"):
            self.info_label.configure(text=info_text)

    def _save_name(self) -> None:
        """
        Στέλνει νέο friendly name για τον client.
        """

        new_name = self.rename_entry.get().strip()

        if not new_name:
            return

        if self.on_rename_callback:
            self.on_rename_callback(self.client_code, new_name)