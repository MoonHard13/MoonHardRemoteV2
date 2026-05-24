import uuid
from typing import Callable

import customtkinter as ctk
from tkinter import filedialog


class ClientManageWindow(ctk.CTkToplevel):
    """
    Παράθυρο διαχείρισης ενός συγκεκριμένου client.
    Οι λειτουργίες είναι οργανωμένες σε tabs.
    """

    def __init__(
        self,
        parent,
        client: dict,
        on_rename_callback: Callable[[str, str], None] | None = None,
        on_terminal_command_callback: Callable[[dict], None] | None = None,
        on_sql_execute_callback: Callable[[dict], None] | None = None
        
    ) -> None:
        """
        Δημιουργεί το παράθυρο διαχείρισης client.
        """

        super().__init__(parent)

        self.client = client
        self.on_rename_callback = on_rename_callback
        self.on_terminal_command_callback = on_terminal_command_callback
        self.on_sql_execute_callback = on_sql_execute_callback

        self.client_code = client.get("client_code", "")
        self.current_directory = ""
        self.command_history: list[str] = []
        self.history_index: int | None = None
        self.appsettings_data: dict = {}
        self.bo_connections: list[dict] = []
        self.selected_bo_connection_id: int = 1
        self.sql_history: list[str] = []
        self.current_sql_request_id: str = ""

        self.title(f"Manage Client - {client.get('display_name') or client.get('pc_name')}")
        self.geometry("1000x700")
        self.minsize(900, 600)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό UI με tabs.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.tabs = ctk.CTkTabview(self, corner_radius=16)
        self.tabs.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.overview_tab = self.tabs.add("Overview")
        self.terminal_tab = self.tabs.add("Terminal")
        self.appsettings_tab = self.tabs.add("AppSettings")

        self.overview_tab.grid_columnconfigure(0, weight=1)
        self.terminal_tab.grid_columnconfigure(0, weight=1)
        self.terminal_tab.grid_rowconfigure(1, weight=1)
        self.appsettings_tab.grid_columnconfigure(0, weight=1)
        self.appsettings_tab.grid_rowconfigure(1, weight=1)
        self.sql_tab = self.tabs.add("SQL")
        self.sql_tab.grid_columnconfigure(0, weight=1)
        self.sql_tab.grid_rowconfigure(2, weight=1)

        self._build_overview_tab()
        self._build_terminal_tab()
        self._build_appsettings_tab()
        self._build_sql_tab()

    def _build_header(self) -> None:
        """
        Δημιουργεί την κεφαλίδα του παραθύρου.
        """

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        status = self.client.get("status", "-")

        header = ctk.CTkFrame(self, corner_radius=16)
        header.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
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

    def _build_overview_tab(self) -> None:
        """
        Δημιουργεί το Overview tab με βασικές πληροφορίες και rename.
        """

        frame = ctk.CTkFrame(self.overview_tab, corner_radius=16)
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

    def _build_terminal_tab(self) -> None:
        """
        Δημιουργεί το Terminal tab.
        """

        top_frame = ctk.CTkFrame(self.terminal_tab, fg_color="transparent")
        top_frame.grid(row=0, column=0, padx=15, pady=(15, 8), sticky="ew")
        top_frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="Remote Terminal",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, sticky="w")

        self.shell_option = ctk.CTkOptionMenu(
            top_frame,
            values=["cmd", "powershell"]
        )
        self.shell_option.set("cmd")
        self.shell_option.grid(row=0, column=1, sticky="e")

        self.output_box = ctk.CTkTextbox(
            self.terminal_tab,
            font=("Consolas", 13),
            wrap="word"
        )
        self.output_box.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.output_box.configure(state="disabled")

        bottom = ctk.CTkFrame(self.terminal_tab, fg_color="transparent")
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
        
    def _build_appsettings_tab(self) -> None:
        """
        Δημιουργεί το AppSettings tab.
        """

        top_frame = ctk.CTkFrame(self.appsettings_tab, corner_radius=16)
        top_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="AppSettings Production JSON",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=3, padx=18, pady=(18, 8), sticky="w")

        self.appsettings_status_label = ctk.CTkLabel(
            top_frame,
            text="Waiting for appsettings data...",
            font=("Segoe UI", 13),
            anchor="w"
        )
        self.appsettings_status_label.grid(row=1, column=0, columnspan=3, padx=18, pady=(0, 10), sticky="ew")

        bo_label = ctk.CTkLabel(
            top_frame,
            text="BO Connection ID:",
            font=("Segoe UI", 14, "bold")
        )
        bo_label.grid(row=2, column=0, padx=(18, 10), pady=(5, 18), sticky="w")

        self.bo_connection_option = ctk.CTkOptionMenu(
            top_frame,
            values=["ID 1"],
            command=self._on_bo_connection_selected
        )
        self.bo_connection_option.set("ID 1")
        self.bo_connection_option.grid(row=2, column=1, padx=(0, 10), pady=(5, 18), sticky="w")

        refresh_button = ctk.CTkButton(
            top_frame,
            text="Refresh Display",
            width=130,
            command=self._refresh_selected_bo_connection
        )
        refresh_button.grid(row=2, column=2, padx=(0, 18), pady=(5, 18), sticky="e")

        self.appsettings_details_box = ctk.CTkTextbox(
            self.appsettings_tab,
            font=("Consolas", 13),
            wrap="word"
        )
        self.appsettings_details_box.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.appsettings_details_box.configure(state="disabled")
        
    def handle_appsettings_result(self, payload: dict) -> None:
        """
        Λαμβάνει τα appsettings από τον server και ενημερώνει το AppSettings tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            message = payload.get("message", "Failed to load appsettings.")
            self._set_appsettings_text(f"ERROR: {message}")
            self.appsettings_status_label.configure(text="Failed to load appsettings.")
            return

        appsettings = payload.get("appsettings") or {}
        self.appsettings_data = appsettings

        file_found = appsettings.get("file_found", False)
        file_path = appsettings.get("file_path") or "-"
        last_read_at = appsettings.get("last_read_at") or "-"

        self.bo_connections = appsettings.get("bo_connections") or []
        self.selected_bo_connection_id = appsettings.get("selected_bo_connection_id") or 1

        if not file_found:
            self.appsettings_status_label.configure(
                text="appsettings.production.json was not found on this client."
            )
            self._set_appsettings_text(
                f"File found: No\n"
                f"Path checked: {file_path}\n"
                f"Last read: {last_read_at}\n"
            )
            return

        bo_values = self._build_bo_connection_values()

        if bo_values:
            self.bo_connection_option.configure(values=bo_values)

            default_value = self._find_bo_option_value(self.selected_bo_connection_id)

            if default_value:
                self.bo_connection_option.set(default_value)
            else:
                self.bo_connection_option.set(bo_values[0])
        else:
            self.bo_connection_option.configure(values=["No BOConnections"])
            self.bo_connection_option.set("No BOConnections")

        if bo_values:
            self.sql_bo_option.configure(values=bo_values)
            self.sql_bo_option.set(self.bo_connection_option.get())
        else:
            self.sql_bo_option.configure(values=["No BOConnections"])
            self.sql_bo_option.set("No BOConnections")

        self.appsettings_status_label.configure(
            text=f"Loaded from: {file_path} | Last read: {last_read_at}"
        )

        self._refresh_selected_bo_connection()
        
    def _refresh_selected_bo_connection(self) -> None:
        """
        Εμφανίζει τα στοιχεία του επιλεγμένου BOConnection.
        """

        appsettings = self.appsettings_data or {}
        summary = appsettings.get("appsettings_summary") or {}
        provider_connections = appsettings.get("provider_connections") or []
        selected_connection = self._get_selected_bo_connection()

        if not appsettings:
            self._set_appsettings_text("No appsettings data loaded yet.")
            return

        if not selected_connection:
            self._set_appsettings_text("No BOConnections found.")
            return

        database_connection = selected_connection.get("DatabaseConnection", "")
        connection_parts = self._parse_connection_string(database_connection)

        provider_text = self._format_provider_connections(provider_connections)

        text = (
            "=== AppSettings Summary ===\n"
            f"AllowedHosts: {summary.get('AllowedHosts')}\n"
            f"MaxRetries: {summary.get('MaxRetries')}\n"
            f"MaxWaitTimePerInvoice: {summary.get('MaxWaitTimePerInvoice')}\n"
            f"Initial Date: {summary.get('initialDate')}\n\n"

            "=== Selected BOConnection ===\n"
            f"ID: {selected_connection.get('ID')}\n"
            f"Server: {connection_parts.get('server')}\n"
            f"Database: {connection_parts.get('database')}\n"
            f"User ID: {connection_parts.get('user_id')}\n"
            f"Password: {connection_parts.get('password')}\n"
            f"UserOID: {selected_connection.get('UserOID')}\n"
            f"Email: {selected_connection.get('email')}\n"
            f"ClientAuth: {selected_connection.get('ClientAuth')}\n"
            f"SubscriptionKey: {selected_connection.get('subscriptionKey')}\n\n"

            "=== Full DatabaseConnection ===\n"
            f"{database_connection}\n\n"

            "=== ProviderConnections ===\n"
            f"{provider_text}\n"
        )

        self._set_appsettings_text(text)

    def _format_provider_connections(self, provider_connections: list[dict]) -> str:
        """
        Μορφοποιεί τα ProviderConnections για προβολή.
        """

        if not provider_connections:
            return "No ProviderConnections found."

        lines: list[str] = []

        for provider in provider_connections:
            lines.append(
                f"ID: {provider.get('ID')}\n"
                f"BaseURL: {provider.get('BaseURL')}\n"
                f"OfflineURL: {provider.get('OfflineURL')}\n"
            )

        return "\n".join(lines)

    def _parse_connection_string(self, connection_string: str) -> dict[str, str | None]:
        """
        Αναλύει SQL Server connection string για εμφάνιση στο dashboard.
        """

        result = {
            "server": None,
            "database": None,
            "user_id": None,
            "password": None
        }

        if not connection_string:
            return result

        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password"
        }

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = key.strip().lower()
            mapped_key = key_map.get(normalized_key)

            if mapped_key:
                result[mapped_key] = value.strip()

        return result

    def _set_appsettings_text(self, text: str) -> None:
        """
        Ενημερώνει το textbox του AppSettings tab.
        """

        self.appsettings_details_box.configure(state="normal")
        self.appsettings_details_box.delete("1.0", "end")
        self.appsettings_details_box.insert("end", text)
        self.appsettings_details_box.configure(state="disabled")
        
    def _build_bo_connection_values(self) -> list[str]:
        """
        Δημιουργεί τις επιλογές BOConnections για το dropdown.
        """

        values: list[str] = []

        for connection in self.bo_connections:
            connection_id = connection.get("ID")
            database_connection = connection.get("DatabaseConnection", "")
            database_name = self._parse_connection_string(database_connection).get("database") or "-"

            values.append(f"ID {connection_id} - {database_name}")

        return values

    def _find_bo_option_value(self, selected_id: int) -> str:
        """
        Βρίσκει την επιλογή dropdown για συγκεκριμένο BOConnection ID.
        """

        selected_id_text = f"ID {selected_id} "

        for value in self._build_bo_connection_values():
            if value.startswith(selected_id_text):
                return value

        return ""

    def _on_bo_connection_selected(self, selected_value: str) -> None:
        """
        Αλλάζει το BOConnection που εμφανίζεται.
        """

        connection_id = self._extract_bo_id_from_option(selected_value)

        if connection_id is not None:
            self.selected_bo_connection_id = connection_id

        self._refresh_selected_bo_connection()

    def _extract_bo_id_from_option(self, selected_value: str) -> int | None:
        """
        Εξάγει το ID από επιλογή τύπου 'ID 1 - DatabaseName'.
        """

        try:
            parts = selected_value.split()
            return int(parts[1])
        except Exception:
            return None

    def _get_selected_bo_connection(self) -> dict:
        """
        Επιστρέφει το επιλεγμένο BOConnection.
        """

        for connection in self.bo_connections:
            if connection.get("ID") == self.selected_bo_connection_id:
                return connection

        return self.bo_connections[0] if self.bo_connections else {}

    def _format_provider_connections(self, provider_connections: list[dict]) -> str:
        """
        Μορφοποιεί τα ProviderConnections για προβολή.
        """

        if not provider_connections:
            return "No ProviderConnections found."

        lines: list[str] = []

        for provider in provider_connections:
            lines.append(
                f"ID: {provider.get('ID')}\n"
                f"BaseURL: {provider.get('BaseURL')}\n"
                f"OfflineURL: {provider.get('OfflineURL')}\n"
            )

        return "\n".join(lines)

    def _parse_connection_string(self, connection_string: str) -> dict[str, str | None]:
        """
        Αναλύει SQL Server connection string για εμφάνιση στο dashboard.
        """

        result = {
            "server": None,
            "database": None,
            "user_id": None,
            "password": None
        }

        if not connection_string:
            return result

        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password"
        }

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = key.strip().lower()
            mapped_key = key_map.get(normalized_key)

            if mapped_key:
                result[mapped_key] = value.strip()

        return result

    def _set_appsettings_text(self, text: str) -> None:
        """
        Ενημερώνει το textbox του AppSettings tab.
        """

        self.appsettings_details_box.configure(state="normal")
        self.appsettings_details_box.delete("1.0", "end")
        self.appsettings_details_box.insert("end", text)
        self.appsettings_details_box.configure(state="disabled")
        
    def _build_sql_tab(self) -> None:
        """
        Δημιουργεί SQL tab για εκτέλεση queries και .sql files.
        """

        top_frame = ctk.CTkFrame(self.sql_tab, corner_radius=16)
        top_frame.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            top_frame,
            text="SQL Server Query Executor",
            font=("Segoe UI", 20, "bold")
        )
        title.grid(row=0, column=0, columnspan=6, padx=18, pady=(18, 8), sticky="w")

        bo_label = ctk.CTkLabel(
            top_frame,
            text="BOConnection:",
            font=("Segoe UI", 14, "bold")
        )
        bo_label.grid(row=1, column=0, padx=(18, 10), pady=(5, 18), sticky="w")

        self.sql_bo_option = ctk.CTkOptionMenu(
            top_frame,
            values=["ID 1"],
            command=self._on_sql_bo_selected
        )
        self.sql_bo_option.set("ID 1")
        self.sql_bo_option.grid(row=1, column=1, padx=(0, 10), pady=(5, 18), sticky="w")

        test_connection_button = ctk.CTkButton(
            top_frame,
            text="Test Connection",
            width=130,
            command=self.test_sql_connection
        )
        test_connection_button.grid(row=1, column=2, padx=(0, 10), pady=(5, 18))

        load_file_button = ctk.CTkButton(
            top_frame,
            text="Load .sql",
            width=100,
            command=self._load_sql_file
        )
        load_file_button.grid(row=1, column=3, padx=(0, 10), pady=(5, 18))

        execute_button = ctk.CTkButton(
            top_frame,
            text="Execute",
            width=100,
            command=self.execute_sql
        )
        execute_button.grid(row=1, column=4, padx=(0, 10), pady=(5, 18))

        self.stop_sql_button = ctk.CTkButton(
            top_frame,
            text="Stop",
            width=90,
            command=self.stop_sql_execution,
            state="disabled"
        )
        self.stop_sql_button.grid(row=1, column=5, padx=(0, 18), pady=(5, 18))

        self.sql_editor = ctk.CTkTextbox(
            self.sql_tab,
            font=("Consolas", 13),
            wrap="none"
        )
        self.sql_editor.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="nsew")
        self.sql_editor.insert("1.0", "SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES;")

        self.sql_result_box = ctk.CTkTextbox(
            self.sql_tab,
            font=("Consolas", 13),
            wrap="none"
        )
        self.sql_result_box.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.sql_result_box.configure(state="disabled")
        
    def _on_sql_bo_selected(self, selected_value: str) -> None:
        """
        Επιλέγει BOConnection ID για SQL εκτέλεση.
        """

        connection_id = self._extract_bo_id_from_option(selected_value)

        if connection_id is not None:
            self.selected_bo_connection_id = connection_id

    def _load_sql_file(self) -> None:
        """
        Φορτώνει .sql αρχείο στο SQL editor.
        """

        file_path = filedialog.askopenfilename(
            title="Select SQL file",
            filetypes=[("SQL files", "*.sql"), ("All files", "*.*")]
        )

        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as file:
                content = file.read()

            self.sql_editor.delete("1.0", "end")
            self.sql_editor.insert("1.0", content)
            self._set_sql_result_text(f"Loaded SQL file:\n{file_path}\n")

        except Exception as exc:
            self._set_sql_result_text(f"Failed to load SQL file:\n{exc}\n")

    def execute_sql(self) -> None:
        """
        Στέλνει SQL query για εκτέλεση στον client.
        """

        sql_text = self.sql_editor.get("1.0", "end").strip()

        if not sql_text:
            self._set_sql_result_text("SQL text is empty.\n")
            return

        request_id = str(uuid.uuid4())
        self.current_sql_request_id = request_id
        self.stop_sql_button.configure(state="normal")

        self._set_sql_result_text(
            f"Executing SQL on BOConnection ID {self.selected_bo_connection_id}...\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_execute",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "bo_connection_id": self.selected_bo_connection_id,
                    "sql_text": sql_text,
                    "timeout": 120
                }
            )

    def handle_sql_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτελέσματα SQL εκτέλεσης.
        """

        if payload.get("client_code") != self.client_code:
            return

        success = payload.get("success")
        error = payload.get("error")
        batches = payload.get("batches") or []

        lines: list[str] = []

        lines.append(f"Success: {success}")
        lines.append(f"BOConnection ID: {payload.get('bo_connection_id')}")
        lines.append(f"Driver: {payload.get('driver')}")
        lines.append(f"Elapsed: {payload.get('elapsed_ms')} ms")

        if error:
            lines.append(f"Error: {error}")

        lines.append("")

        for batch in batches:
            lines.append(f"=== Batch {batch.get('batch_index')} ===")

            if batch.get("error"):
                lines.append(f"Batch error: {batch.get('error')}")

            result_sets = batch.get("result_sets") or []

            if not result_sets:
                lines.append(f"Rows affected: {batch.get('rowcount')}")
                lines.append("")
                continue

            for result_index, result_set in enumerate(result_sets, start=1):
                columns = result_set.get("columns") or []
                rows = result_set.get("rows") or []

                lines.append(f"--- Result Set {result_index} | Rows: {len(rows)} ---")
                lines.append(" | ".join(columns))
                lines.append("-" * 100)

                for row in rows[:500]:
                    lines.append(" | ".join(str(value) for value in row))

                if len(rows) > 500:
                    lines.append(f"... truncated. Showing first 500 of {len(rows)} rows.")

                lines.append("")

        self._set_sql_result_text("\n".join(lines))
        self.stop_sql_button.configure(state="disabled")
        self.current_sql_request_id = ""

    def handle_sql_error(self, payload: dict) -> None:
        """
        Εμφανίζει SQL routing/server error.
        """

        self._set_sql_result_text(
            f"SQL ERROR:\n{payload.get('message', 'Unknown SQL error.')}\n"
        )

    def _set_sql_result_text(self, text: str) -> None:
        """
        Ενημερώνει το SQL result textbox.
        """

        self.sql_result_box.configure(state="normal")
        self.sql_result_box.delete("1.0", "end")
        self.sql_result_box.insert("end", text)
        self.sql_result_box.configure(state="disabled")
        
    def test_sql_connection(self) -> None:
        """
        Στέλνει αίτημα δοκιμής SQL σύνδεσης για το επιλεγμένο BOConnection.
        """

        request_id = str(uuid.uuid4())
        self.current_sql_request_id = request_id

        self._set_sql_result_text(
            f"Testing SQL connection on BOConnection ID {self.selected_bo_connection_id}...\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_test_connection",
                    "request_id": request_id,
                    "client_code": self.client_code,
                    "bo_connection_id": self.selected_bo_connection_id,
                    "timeout": 15
                }
            )
            
    def stop_sql_execution(self) -> None:
        """
        Στέλνει αίτημα ακύρωσης του τρέχοντος SQL query.
        """

        if not self.current_sql_request_id:
            self._set_sql_result_text("No active SQL request to stop.\n")
            return

        self._set_sql_result_text(
            f"Stopping SQL request: {self.current_sql_request_id}\n"
        )

        if self.on_sql_execute_callback:
            self.on_sql_execute_callback(
                {
                    "type": "sql_cancel",
                    "request_id": self.current_sql_request_id,
                    "client_code": self.client_code
                }
            )
            
    def handle_sql_test_connection_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα δοκιμής SQL σύνδεσης.
        """

        if payload.get("client_code") != self.client_code:
            return

        text = (
            "=== SQL Connection Test ===\n"
            f"Success: {payload.get('success')}\n"
            f"BOConnection ID: {payload.get('bo_connection_id')}\n"
            f"Driver: {payload.get('driver')}\n"
            f"Elapsed: {payload.get('elapsed_ms')} ms\n"
            f"Server: {payload.get('server_name')}\n"
            f"Database: {payload.get('database_name')}\n"
            f"Login: {payload.get('login_name')}\n"
        )

        if payload.get("error"):
            text += f"\nError:\n{payload.get('error')}\n"

        self._set_sql_result_text(text)


    def handle_sql_cancel_result(self, payload: dict) -> None:
        """
        Εμφανίζει αποτέλεσμα ακύρωσης SQL query.
        """

        if payload.get("client_code") != self.client_code:
            return

        self.stop_sql_button.configure(state="disabled")

        self._set_sql_result_text(
            "=== SQL Cancel Result ===\n"
            f"Success: {payload.get('success')}\n"
            f"Message: {payload.get('message')}\n"
        )