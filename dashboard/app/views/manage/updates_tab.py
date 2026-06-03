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
        self.latest_update_payload: dict = {}
        self.latest_download_payload: dict = {}
        self.latest_extract_payload: dict = {}
        
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

        self.download_button = ctk.CTkButton(
            top_frame,
            text="Download Package",
            width=160,
            command=self.request_update_download,
            state="disabled",
            **secondary_button_style()
        )
        self.download_button.grid(row=0, column=2, padx=(0, 18), pady=(16, 4), sticky="e")

        self.extract_button = ctk.CTkButton(
            top_frame,
            text="Extract Package",
            width=150,
            command=self.request_update_extract,
            state="disabled",
            **secondary_button_style()
        )
        self.extract_button.grid(row=0, column=3, padx=(0, 18), pady=(16, 4), sticky="e")

        self.apply_button = ctk.CTkButton(
            top_frame,
            text="Apply Update",
            width=140,
            command=self.request_update_apply,
            state="disabled",
            **primary_button_style()
        )
        self.apply_button.grid(row=0, column=4, padx=(0, 18), pady=(16, 4), sticky="e")

        clear_button = ctk.CTkButton(
            top_frame,
            text="Clear",
            width=90,
            command=self.clear_result,
            **secondary_button_style()
        )
        clear_button.grid(row=1, column=4, padx=(0, 18), pady=(0, 16), sticky="e")

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
        self.latest_update_payload = payload

        can_download = (
            update_available
            and bool(payload.get("download_url"))
            and bool(payload.get("sha256"))
        )

        self.download_button.configure(
            state="normal" if can_download else "disabled"
        )
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

        self.latest_download_payload = {}
        self.download_button.configure(state="disabled")
        self.extract_button.configure(state="disabled")
        self.latest_extract_payload = {}
        self.apply_button.configure(state="disabled")

    def _set_result_text(self, text: str) -> None:
        """
        Ενημερώνει το textbox αποτελέσματος.
        """

        self.result_textbox.configure(state="normal")
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", text)
        self.result_textbox.configure(state="disabled")
        
    def request_update_download(self) -> None:
        """
        Στέλνει request για download update package στον client.
        """

        if not self.latest_update_payload:
            self.status_label.configure(
                text="Run update check first.",
                text_color=COLORS.danger
            )
            return

        download_url = self.latest_update_payload.get("download_url", "")
        sha256 = self.latest_update_payload.get("sha256", "")
        latest_version = self.latest_update_payload.get("latest_version", "")

        if not download_url or not sha256:
            self.status_label.configure(
                text="Missing download URL or SHA256.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Downloading update package...",
            text_color=COLORS.accent
        )

        if self.on_update_request_callback:
            self.on_update_request_callback(
                {
                    "type": "client_update_download",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "download_url": download_url,
                    "sha256": sha256,
                    "latest_version": latest_version
                }
            )
            
    def handle_update_download_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα download update package.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            error = payload.get("error", "Unknown download error.")
            self.status_label.configure(
                text=f"Download failed: {error}",
                text_color=COLORS.danger
            )
            self._set_result_text(f"Download failed:\n\n{error}")
            return

        self.status_label.configure(
            text="Download completed and SHA256 verified.",
            text_color=COLORS.success
        )

        self.latest_download_payload = payload
        self.extract_button.configure(state="normal")

        result_text = (
            "=== Update Package Download ===\n\n"
            f"Latest version:      {payload.get('latest_version', '-')}\n"
            f"Saved path:          {payload.get('saved_path', '-')}\n"
            f"File size bytes:     {payload.get('file_size_bytes', '-')}\n"
            f"SHA256 verified:     {'Yes' if payload.get('sha256_verified') else 'No'}\n\n"
            "=== Hash Info ===\n\n"
            f"Expected SHA256: {payload.get('expected_sha256', '-')}\n"
            f"Actual SHA256:   {payload.get('actual_sha256', '-')}\n\n"
            "The package was downloaded only. It has not been installed yet.\n"
        )

        self._set_result_text(result_text)
        
    def request_update_extract(self) -> None:
        """
        Στέλνει request για extract και validation του update package.
        """

        if not self.latest_download_payload:
            self.status_label.configure(
                text="Download package first.",
                text_color=COLORS.danger
            )
            return

        package_path = self.latest_download_payload.get("saved_path", "")
        latest_version = self.latest_download_payload.get("latest_version", "")

        if not package_path:
            self.status_label.configure(
                text="Missing downloaded package path.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Extracting update package...",
            text_color=COLORS.accent
        )

        if self.on_update_request_callback:
            self.on_update_request_callback(
                {
                    "type": "client_update_extract",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "package_path": package_path,
                    "latest_version": latest_version
                }
            )
            
    def request_update_apply(self) -> None:
        """
        Στέλνει request για silent apply του extracted update package.
        """

        if not self.latest_extract_payload:
            self.status_label.configure(
                text="Extract package first.",
                text_color=COLORS.danger
            )
            return

        extracted_path = self.latest_extract_payload.get("extracted_path", "")
        latest_version = self.latest_extract_payload.get("latest_version", "")

        if not extracted_path:
            self.status_label.configure(
                text="Missing extracted package path.",
                text_color=COLORS.danger
            )
            return

        request_id = str(uuid.uuid4())

        self.status_label.configure(
            text="Starting silent updater on client...",
            text_color=COLORS.accent
        )

        self.apply_button.configure(state="disabled")

        if self.on_update_request_callback:
            self.on_update_request_callback(
                {
                    "type": "client_update_apply",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "extracted_path": extracted_path,
                    "latest_version": latest_version
                }
            )
            
    def handle_update_apply_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα εκκίνησης του silent updater.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            error = payload.get("error", "Unknown apply error.")
            self.status_label.configure(
                text=f"Apply failed to start: {error}",
                text_color=COLORS.danger
            )
            self._set_result_text(f"Apply failed to start:\n\n{error}")
            self.apply_button.configure(state="normal")
            return

        self.status_label.configure(
            text="Silent updater started. Waiting for client reconnect...",
            text_color=COLORS.warning
        )

        result_text = (
            "=== Apply Update Started ===\n\n"
            f"Latest version:   {payload.get('latest_version', '-')}\n"
            f"Extracted path:   {payload.get('extracted_path', '-')}\n"
            f"Updater path:     {payload.get('updater_path', '-')}\n\n"
            "The updater was started silently on the client.\n"
            "The client service will stop, update files, start again, and reconnect.\n\n"
            "This window may temporarily show the client as offline during update.\n"
        )

        self._set_result_text(result_text)