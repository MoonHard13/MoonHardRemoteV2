import uuid
from typing import Callable, Any

import customtkinter as ctk
from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    primary_button_style
)


class TerminalTab(ctk.CTkFrame):
    """
    Terminal tab για αποστολή remote commands στον client.
    Περιλαμβάνει command history και autocomplete.
    """

    def __init__(
        self,
        parent,
        client_code: str,
        on_terminal_command_callback: Callable[[dict], None] | None = None,
        on_terminal_autocomplete_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το Terminal tab.
        """

        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self.client_code = client_code
        self.on_terminal_command_callback = on_terminal_command_callback
        self.on_terminal_autocomplete_callback = on_terminal_autocomplete_callback

        self.current_directory = ""
        self.last_autocomplete_request_id: str = ""
        self.autocomplete_matches: list[str] = []
        self.autocomplete_index: int = 0
        self.command_history: list[str] = []
        self.history_index: int | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_ui()


    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του Terminal tab.
        """

        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=(SPACING.card_padding, SPACING.inner_padding),
            sticky="ew"
        )
        top_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Remote Terminal",
            font=FONTS.subtitle,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, sticky="w")

        self.shell_option = ctk.CTkOptionMenu(
            top_frame,
            values=["cmd", "powershell"],
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover
        )
        self.shell_option.set("cmd")
        self.shell_option.grid(row=0, column=1, sticky="e")

        self.output_box = ctk.CTkTextbox(
            self,
            font=FONTS.mono_body,
            wrap="word",
            fg_color="#050A0C",
            text_color=COLORS.text_primary,
            border_color=COLORS.border,
            border_width=1
        )
        self.output_box.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.inner_padding),
            sticky="nsew"
        )
        self.output_box.configure(state="disabled")

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(
            row=2,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="ew"
        )
        bottom.grid_columnconfigure(0, weight=1)

        self.command_entry = ctk.CTkEntry(
            bottom,
            placeholder_text="Type command...",
            fg_color=COLORS.surface_light,
            border_color=COLORS.border,
            text_color=COLORS.text_primary,
            placeholder_text_color=COLORS.text_muted
        )
        self.command_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.command_entry.bind("<Return>", lambda _event: self.send_terminal_command())
        self.command_entry.bind("<Up>", self._show_previous_command)
        self.command_entry.bind("<Down>", self._show_next_command)
        self.command_entry.bind("<Tab>", self._request_terminal_autocomplete)

        send_button = ctk.CTkButton(
            bottom,
            text="Send",
            width=100,
            command=self.send_terminal_command,
            **primary_button_style()
        )
        send_button.grid(row=0, column=1)


    def send_terminal_command(self) -> None:
        """
        Στέλνει terminal command για τον συγκεκριμένο client.
        """

        command = self.command_entry.get().strip()

        if not command:
            return

        self._add_command_to_history(command)

        command_id = str(uuid.uuid4())
        shell = self.shell_option.get()

        self.append_output(f"\n[{shell}] {self.current_directory}> {command}\n")
        self.command_entry.delete(0, "end")

        if self.on_terminal_command_callback:
            self.on_terminal_command_callback(
                {
                    "type": "terminal_command",
                    "command_id": command_id,
                    "client_code": self.client_code,
                    "shell": shell,
                    "command": command
                }
            )


    def handle_terminal_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα terminal command.
        """

        if payload.get("client_code") != self.client_code:
            return

        stdout = payload.get("stdout", "")
        stderr = payload.get("stderr", "")
        exit_code = payload.get("exit_code", "")
        current_directory = payload.get("current_directory", "")

        if current_directory:
            self.current_directory = current_directory

        if stdout:
            self.append_output(stdout)

            if not stdout.endswith("\n"):
                self.append_output("\n")

        if stderr:
            self.append_output(stderr)

            if not stderr.endswith("\n"):
                self.append_output("\n")

        self.append_output(f"[exit_code={exit_code}] cwd={self.current_directory}\n")


    def handle_terminal_error(self, payload: dict) -> None:
        """
        Εμφανίζει σφάλμα terminal.
        """

        self.append_output(f"ERROR: {payload.get('message', 'Unknown error.')}\n")


    def append_output(self, text: str) -> None:
        """
        Προσθέτει κείμενο στο terminal output.
        """

        self.output_box.configure(state="normal")
        self.output_box.insert("end", text)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")


    def _add_command_to_history(self, command: str) -> None:
        """
        Αποθηκεύει την εντολή στο ιστορικό.
        """

        if self.command_history and self.command_history[-1] == command:
            self.history_index = None
            return

        self.command_history.append(command)
        self.history_index = None


    def _show_previous_command(self, _event=None) -> str:
        """
        Φέρνει προηγούμενη εντολή.
        """

        if not self.command_history:
            return "break"

        if self.history_index is None:
            self.history_index = len(self.command_history) - 1
        elif self.history_index > 0:
            self.history_index -= 1

        self._set_command_entry(self.command_history[self.history_index])
        return "break"


    def _show_next_command(self, _event=None) -> str:
        """
        Φέρνει επόμενη εντολή.
        """

        if not self.command_history:
            return "break"

        if self.history_index is None:
            return "break"

        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self._set_command_entry(self.command_history[self.history_index])
        else:
            self.history_index = None
            self._set_command_entry("")

        return "break"


    def _set_command_entry(self, command: str) -> None:
        """
        Βάζει εντολή στο input.
        """

        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, command)
        self.command_entry.icursor("end")


    def _request_terminal_autocomplete(self, _event=None) -> str:
        """
        Στέλνει αίτημα autocomplete για το Remote Terminal.
        """

        command_text = self.command_entry.get()
        shell = self.shell_option.get()

        if not command_text.strip():
            return "break"

        request_id = str(uuid.uuid4())
        self.last_autocomplete_request_id = request_id
        self.autocomplete_matches = []
        self.autocomplete_index = 0

        if self.on_terminal_autocomplete_callback:
            self.on_terminal_autocomplete_callback(
                {
                    "type": "terminal_autocomplete",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "shell": shell,
                    "command_text": command_text
                }
            )

        return "break"


    def handle_terminal_autocomplete_result(self, payload: dict[str, Any]) -> None:
        """
        Εφαρμόζει autocomplete αποτέλεσμα στο terminal input.
        """

        if payload.get("client_code") != self.client_code:
            return

        if payload.get("request_id") != self.last_autocomplete_request_id:
            return

        matches = payload.get("matches") or []

        if not matches:
            return

        self.autocomplete_matches = matches
        self.autocomplete_index = 0
        self._apply_autocomplete_match(matches[0])


    def handle_terminal_autocomplete_error(self, payload: dict[str, Any]) -> None:
        """
        Εμφανίζει σφάλμα autocomplete.
        """

        if payload.get("client_code") != self.client_code:
            return

        self.append_output(
            f"\nAutocomplete error: {payload.get('message', 'Unknown error.')}\n"
        )


    def _apply_autocomplete_match(self, match) -> None:
        """
        Εφαρμόζει autocomplete κρατώντας το προηγούμενο command prefix.
        Παράδειγμα:
        cd de + Desktop\\ = cd Desktop\\
        """

        current_text = self.command_entry.get()

        if isinstance(match, dict):
            insert_value = match.get("insert_value") or match.get("name") or ""
        else:
            insert_value = str(match)

        if not insert_value:
            return

        command_prefix, _, _partial_value = current_text.rpartition(" ")

        if command_prefix:
            new_text = f"{command_prefix} {insert_value}"
        else:
            new_text = insert_value

        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, new_text)
        self.command_entry.icursor("end")