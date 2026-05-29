import uuid
from typing import Callable

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    card_style,
    primary_button_style,
    secondary_button_style
)


class UpdatesTab(ctk.CTkFrame):
    """
    Tab για έλεγχο έκδοσης και μελλοντικό auto update του client.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        on_update_request_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Updates tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_update_request_callback = on_update_request_callback

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του Updates tab.
        """

        top_frame = ctk.CTkFrame(self, **card_style())
        top_frame.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=SPACING.card_padding,
            sticky="ew"
        )
        top_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Client Updates",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")

        self.status_label = ctk.CTkLabel(
            top_frame,
            text="Ready",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        self.status_label.grid(row=1, column=0, padx=18, pady=(0, 16), sticky="w")

        check_button = ctk.CTkButton(
            top_frame,
            text="Check for Update",
            width=160,
            command=self.request_update_check,
            **primary_button_style()
        )
        check_button.grid(row=0, column=1, padx=(0, 18), pady=(16, 4), sticky="e")

        clear_button = ctk.CTkButton(
            top_frame,
            text="Clear",
            width=90,
            command=self.clear_result,
            **secondary_button_style()
        )
        clear_button.grid(row=1, column=1, padx=(0, 18), pady=(0, 16), sticky="e")

        result_frame = ctk.CTkFrame(self, **card_style())
        result_frame.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="nsew"
        )
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(0, weight=1)

        self.result_textbox = ctk.CTkTextbox(
            result_frame,
            fg_color=COLORS.background,
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1,
            font=FONTS.mono_body,
            wrap="word"
        )
        self.result_textbox.grid(
            row=0,
            column=0,
            padx=14,
            pady=14,
            sticky="nsew"
        )
        self._set_result_text(
            "No update check has been performed yet.\n\n"
            "Press 'Check for Update' to compare this client with the server manifest."
        )

    def request_update_check(self) -> None:
        """
        Στέλνει request για έλεγχο update.
        """

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Checking for update...",
            text_color=COLORS.accent
        )

        if self.on_update_request_callback:
            self.on_update_request_callback(
                {
                    "type": "client_update_check",
                    "request_id": request_id,
                    "client_code": self.client_code
                }
            )

    def handle_update_check_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα ελέγχου update.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            error = payload.get("error", "Unknown update check error.")
            self.status_label.configure(
                text=f"Update check failed: {error}",
                text_color=COLORS.danger
            )
            self._set_result_text(f"Update check failed:\n\n{error}")
            return

        update_available = bool(payload.get("update_available", False))
        status_text = "Update available" if update_available else "Client is up to date"
        status_color = COLORS.warning if update_available else COLORS.success

        self.status_label.configure(
            text=status_text,
            text_color=status_color
        )

        result_text = (
            "=== Client Update Check ===\n\n"
            f"Current client version: {payload.get('current_version', '-')}\n"
            f"Latest server version:  {payload.get('latest_version', '-')}\n"
            f"Update available:       {'Yes' if update_available else 'No'}\n"
            f"Mandatory:              {'Yes' if payload.get('mandatory') else 'No'}\n\n"
            "=== Package Info ===\n\n"
            f"Download URL: {payload.get('download_url') or '-'}\n"
            f"SHA256:       {payload.get('sha256') or '-'}\n"
            f"Manifest URL: {payload.get('manifest_url') or '-'}\n\n"
            "=== Release Notes ===\n\n"
            f"{payload.get('release_notes') or '-'}\n"
        )

        self._set_result_text(result_text)

    def clear_result(self) -> None:
        """
        Καθαρίζει το αποτέλεσμα ελέγχου update.
        """

        self.status_label.configure(
            text="Ready",
            text_color=COLORS.text_secondary
        )

        self._set_result_text(
            "No update check has been performed yet.\n\n"
            "Press 'Check for Update' to compare this client with the server manifest."
        )

    def _set_result_text(self, text: str) -> None:
        """
        Ενημερώνει το textbox αποτελέσματος.
        """

        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", text)
        self.result_textbox.configure(state="disabled")