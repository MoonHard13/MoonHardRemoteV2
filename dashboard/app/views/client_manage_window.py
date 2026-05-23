import uuid
from typing import Callable

import customtkinter as ctk


class ClientManageWindow(ctk.CTkToplevel):
    """
    Παράθυρο διαχείρισης ενός συγκεκριμένου client.
    Περιλαμβάνει rename και remote terminal για τον συγκεκριμένο client.
    """

    def __init__(
        self,
        parent,
        client: dict,
        on_rename_callback: Callable[[str, str], None] | None = None,
        on_terminal_command_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το παράθυρο διαχείρισης client.
        """

        super().__init__(parent)

        self.client = client
        self.on_rename_callback = on_rename_callback
        self.on_terminal_command_callback = on_terminal_command_callback

        self.client_code = client.get("client_code", "")
        self.current_directory = ""
        self.command_history: list[str] = []
        self.history_index: int | None = None

        self.title(f"Manage Client - {client.get('display_name') or client.get('pc_name')}")
        self.geometry("950x650")
        self.minsize(850, 550)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το UI του παραθύρου.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        status = self.client.get("status", "-")

        header = ctk.CTkFrame(self, corner_radius=16)
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text=display_name,
            font=("Segoe UI", 24, "bold")
        )
        title.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        info = ctk.CTkLabel(
            header,
            text=f"PC: {pc_name} | User: {username} | Status: {status} | Code: {self.client_code}",
            font=("Segoe UI", 13),
            anchor="w"
        )
        info.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

        actions = ctk.CTkFrame(self, corner_radius=16)
        actions.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)

        self.rename_entry = ctk.CTkEntry(
            actions,
            placeholder_text="Friendly name"
        )
        self.rename_entry.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        self.rename_entry.insert(0, display_name)

        rename_button = ctk.CTkButton(
            actions,
            text="Save Name",
            width=120,
            command=self._save_name
        )
        rename_button.grid(row=0, column=1, padx=(0, 15), pady=15)

        terminal = ctk.CTkFrame(self, corner_radius=16)
        terminal.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")
        terminal.grid_columnconfigure(0, weight=1)
        terminal.grid_rowconfigure(1, weight=1)

        terminal_top = ctk.CTkFrame(terminal, fg_color="transparent")
        terminal_top.grid(row=0, column=0, padx=15, pady=(15, 8), sticky="ew")
        terminal_top.grid_columnconfigure(0, weight=1)

        terminal_title = ctk.CTkLabel(
            terminal_top,
            text="Remote Terminal",
            font=("Segoe UI", 18, "bold")
        )
        terminal_title.grid(row=0, column=0, sticky="w")

        self.shell_option = ctk.CTkOptionMenu(
            terminal_top,
            values=["cmd", "powershell"]
        )
        self.shell_option.set("cmd")
        self.shell_option.grid(row=0, column=1, sticky="e")

        self.output_box = ctk.CTkTextbox(
            terminal,
            font=("Consolas", 13),
            wrap="word"
        )
        self.output_box.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.output_box.configure(state="disabled")

        bottom = ctk.CTkFrame(terminal, fg_color="transparent")
        bottom.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.command_entry = ctk.CTkEntry(
            bottom,
            placeholder_text="Type command for this client..."
        )
        self.command_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.command_entry.bind("<Return>", lambda _event: self.send_terminal_command())
        self.command_entry.bind("<Up>", self._show_previous_command)
        self.command_entry.bind("<Down>", self._show_next_command)

        send_button = ctk.CTkButton(
            bottom,
            text="Send",
            width=100,
            command=self.send_terminal_command
        )
        send_button.grid(row=0, column=1)

    def _save_name(self) -> None:
        """
        Στέλνει αίτημα αλλαγής φιλικού ονόματος.
        """

        new_name = self.rename_entry.get().strip()

        if not new_name:
            self.append_output("ERROR: Name cannot be empty.\n")
            return

        if self.on_rename_callback:
            self.on_rename_callback(self.client_code, new_name)

        self.append_output(f"Rename request sent: {new_name}\n")

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