from typing import Callable

import customtkinter as ctk


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

        frame = ctk.CTkFrame(self, corner_radius=16)
        frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            frame,
            text="Client Information",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 8), sticky="w")

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        app_version = self.client.get("app_version", "-")
        last_seen = self.client.get("last_seen", "-")

        info_text = (
            f"Display name: {display_name}\n"
            f"PC name: {pc_name}\n"
            f"Username: {username}\n"
            f"App version: {app_version}\n"
            f"Last seen: {last_seen}"
        )

        info_label = ctk.CTkLabel(
            frame,
            text=info_text,
            font=("Segoe UI", 14),
            justify="left",
            anchor="w"
        )
        info_label.grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 18), sticky="w")

        rename_title = ctk.CTkLabel(
            frame,
            text="Rename Client",
            font=("Segoe UI", 18, "bold")
        )
        rename_title.grid(row=2, column=0, columnspan=2, padx=18, pady=(8, 8), sticky="w")

        self.rename_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Friendly name"
        )
        self.rename_entry.grid(row=3, column=0, padx=(18, 10), pady=(0, 18), sticky="ew")
        self.rename_entry.insert(0, display_name)

        rename_button = ctk.CTkButton(
            frame,
            text="Save Name",
            width=120,
            command=self._save_name
        )
        rename_button.grid(row=3, column=1, padx=(0, 18), pady=(0, 18), sticky="e")


    def _save_name(self) -> None:
        """
        Στέλνει νέο friendly name για τον client.
        """

        new_name = self.rename_entry.get().strip()

        if not new_name:
            return

        if self.on_rename_callback:
            self.on_rename_callback(self.client_code, new_name)