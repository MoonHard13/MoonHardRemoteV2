import uuid
from typing import Callable

import customtkinter as ctk


class TerminalView(ctk.CTkFrame):
    """
    Προβολή Remote Terminal για εκτέλεση CMD/PowerShell εντολών σε client PC.
    """

    def __init__(
        self,
        parent,
        on_command_callback: Callable[[dict], None] | None = None
    ) -> None:
        """
        Δημιουργεί το UI του Remote Terminal.
        """

        super().__init__(parent, corner_radius=18)

        self.on_command_callback = on_command_callback
        self.clients: list[dict] = []
        self.client_name_to_code: dict[str, str] = {}
        self.selected_client_code: str = ""
        self.current_directory: str = ""
        self.command_history: list[str] = []
        self.history_index: int | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί τα widgets του terminal.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        title_label = ctk.CTkLabel(
            self,
            text="Remote Terminal",
            font=("Segoe UI", 22, "bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        controls_frame.grid_columnconfigure(0, weight=1)

        self.client_option = ctk.CTkOptionMenu(
            controls_frame,
            values=["No clients"],
            command=self._on_client_selected
        )
        self.client_option.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="ew")

        self.shell_option = ctk.CTkOptionMenu(
            controls_frame,
            values=["cmd", "powershell"]
        )
        self.shell_option.set("cmd")
        self.shell_option.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="e")

        clear_button = ctk.CTkButton(
            controls_frame,
            text="Clear",
            width=90,
            command=self.clear_output
        )
        clear_button.grid(row=0, column=2, padx=(0, 0), pady=5, sticky="e")

        self.output_box = ctk.CTkTextbox(
            self,
            font=("Consolas", 13),
            wrap="word"
        )
        self.output_box.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="nsew")
        self.output_box.configure(state="disabled")

        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        bottom_frame.grid_columnconfigure(0, weight=1)

        self.command_entry = ctk.CTkEntry(
            bottom_frame,
            placeholder_text="Type CMD/PowerShell command..."
        )
        self.command_entry.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="ew")
        self.command_entry.bind("<Return>", lambda _event: self.send_command())
        self.command_entry.bind("<Up>", self._show_previous_command)
        self.command_entry.bind("<Down>", self._show_next_command)

        send_button = ctk.CTkButton(
            bottom_frame,
            text="Send",
            width=100,
            command=self.send_command
        )
        send_button.grid(row=0, column=1, pady=0, sticky="e")

    def update_clients(self, clients: list[dict]) -> None:
        """
        Ανανεώνει τη λίστα διαθέσιμων clients στο terminal.
        """

        self.clients = clients
        self.client_name_to_code.clear()

        online_clients = [
            client for client in clients
            if str(client.get("status", "")).lower() == "online"
        ]

        values: list[str] = []

        for client in online_clients:
            client_code = client.get("client_code", "")
            display_name = client.get("display_name") or client.get("pc_name") or client_code

            label = f"{display_name} ({client_code})"

            values.append(label)
            self.client_name_to_code[label] = client_code

        if not values:
            self.client_option.configure(values=["No online clients"])
            self.client_option.set("No online clients")
            self.selected_client_code = ""
            return

        self.client_option.configure(values=values)

        if self.selected_client_code not in self.client_name_to_code.values():
            first_label = values[0]
            self.client_option.set(first_label)
            self.selected_client_code = self.client_name_to_code[first_label]

    def _on_client_selected(self, selected_label: str) -> None:
        """
        Ενημερώνει τον επιλεγμένο client.
        """

        self.selected_client_code = self.client_name_to_code.get(selected_label, "")

    def send_command(self) -> None:
        """
        Στέλνει την εντολή terminal στον επιλεγμένο client.
        """

        command = self.command_entry.get().strip()

        if not command:
            return

        self._add_command_to_history(command)

        if not self.selected_client_code:
            self.append_output("No online client selected.\n")
            return

        shell = self.shell_option.get()
        command_id = str(uuid.uuid4())

        self.append_output(
            f"\n[{shell}] {self.current_directory}> {command}\n"
        )

        self.command_entry.delete(0, "end")

        if self.on_command_callback:
            self.on_command_callback(
                {
                    "type": "terminal_command",
                    "command_id": command_id,
                    "client_code": self.selected_client_code,
                    "shell": shell,
                    "command": command
                }
            )

    def handle_terminal_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα εντολής terminal.
        """

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

        message = payload.get("message", "Unknown terminal error.")
        self.append_output(f"ERROR: {message}\n")

    def append_output(self, text: str) -> None:
        """
        Προσθέτει κείμενο στο terminal output.
        """

        self.output_box.configure(state="normal")
        self.output_box.insert("end", text)
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def clear_output(self) -> None:
        """
        Καθαρίζει το terminal output.
        """

        self.output_box.configure(state="normal")
        self.output_box.delete("1.0", "end")
        self.output_box.configure(state="disabled")
        
    def _add_command_to_history(self, command: str) -> None:
        """
        Αποθηκεύει την εντολή στο ιστορικό terminal.
        """

        if not command:
            return

        if self.command_history and self.command_history[-1] == command:
            self.history_index = None
            return

        self.command_history.append(command)
        self.history_index = None


    def _show_previous_command(self, _event=None) -> str:
        """
        Φέρνει την προηγούμενη εντολή με το πάνω βελάκι.
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
        Φέρνει την επόμενη εντολή με το κάτω βελάκι.
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
        Βάζει εντολή στο input του terminal.
        """

        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, command)
        self.command_entry.icursor("end")