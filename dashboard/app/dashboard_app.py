import logging
from typing import Any

import customtkinter as ctk

from app.config import DashboardConfig
from app.views.clients_view import ClientsView
from app.websocket_client import DashboardWebSocketClient
from app.views.client_manage_window import ClientManageWindow


logger = logging.getLogger(__name__)


class MoonHardDashboardApp(ctk.CTk):
    """
    Κεντρικό GUI του MoonHard Remote Dashboard.
    """

    def __init__(self) -> None:
        """
        Δημιουργεί το dashboard και ξεκινά τη WebSocket σύνδεση.
        """

        super().__init__()

        self.config_data = DashboardConfig()
        self.websocket_client: DashboardWebSocketClient | None = None
        self.manage_windows: dict[str, ClientManageWindow] = {}
        
        self.title(self.config_data.app_name)
        self.geometry("1100x700")
        self.minsize(900, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._build_ui()
        self._start_websocket()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό layout του dashboard.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_frame = ctk.CTkFrame(self, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            self.header_frame,
            text="MoonHard Remote v2",
            font=("Segoe UI", 26, "bold")
        )
        title_label.grid(row=0, column=0, padx=25, pady=18, sticky="w")

        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="Σύνδεση...",
            font=("Segoe UI", 14)
        )
        self.status_label.grid(row=0, column=1, padx=25, pady=18, sticky="e")

        self.clients_view = ClientsView(
            self,
            on_manage_callback=self._open_manage_window
        )
        self.clients_view.grid(row=1, column=0, padx=20, pady=20, sticky="nsew")

    def _start_websocket(self) -> None:
        """
        Ξεκινάει τη WebSocket σύνδεση του dashboard.
        """

        self.websocket_client = DashboardWebSocketClient(
            websocket_url=self.config_data.dashboard_websocket_url,
            dashboard_token=self.config_data.dashboard_token,
            on_message_callback=self._handle_websocket_message_threadsafe,
            on_status_callback=self._set_connection_status_threadsafe
        )

        self.websocket_client.start()

    def _handle_websocket_message_threadsafe(self, payload: dict[str, Any]) -> None:
        """
        Μεταφέρει την επεξεργασία WebSocket μηνυμάτων στο κύριο GUI thread.
        """

        self.after(0, lambda: self._handle_websocket_message(payload))

    def _handle_websocket_message(self, payload: dict[str, Any]) -> None:
        """
        Επεξεργάζεται τα μηνύματα που έρχονται από τον server.
        """

        message_type = payload.get("type")

        if message_type == "clients_list":
            clients = payload.get("clients", [])

            self.clients_view.update_clients(clients)

            logger.info("Dashboard clients list updated. Count: %s", len(clients))

        elif message_type == "rename_client_success":
            logger.info("Client renamed successfully.")

        elif message_type == "rename_client_error":
            logger.error("Client rename failed: %s", payload.get("message"))

        elif message_type == "terminal_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_terminal_result(payload)

        elif message_type == "terminal_error":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_terminal_error(payload)

        elif message_type == "terminal_autocomplete_result":
            self.terminal_view.handle_autocomplete_result(payload)

        elif message_type == "terminal_autocomplete_error":
            self.terminal_view.handle_autocomplete_error(payload)

    def _set_connection_status_threadsafe(self, status: str) -> None:
        """
        Μεταφέρει την αλλαγή κατάστασης σύνδεσης στο κύριο GUI thread.
        """

        self.after(0, lambda: self.status_label.configure(text=status))

    def on_close(self) -> None:
        """
        Κλείνει σωστά το dashboard.
        """

        if self.websocket_client:
            self.websocket_client.stop()

        self.destroy()

    def _rename_client(self, client_code: str, display_name: str) -> None:
        """
        Στέλνει αίτημα αλλαγής φιλικού ονόματος client στον server.
        """

        if not self.websocket_client:
            return

        self.websocket_client.send_message(
            {
                "type": "rename_client",
                "client_code": client_code,
                "display_name": display_name
            }
        )

        logger.info(
            "Rename client request sent. client_code=%s display_name=%s",
            client_code,
            display_name
        )
        
    def _send_terminal_command(self, payload: dict[str, Any]) -> None:
        """
        Στέλνει terminal command στον server για εκτέλεση στον επιλεγμένο client.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        self.websocket_client.send_message(payload)

        logger.info(
            "Terminal command sent. client_code=%s shell=%s command=%s",
            payload.get("client_code"),
            payload.get("shell"),
            payload.get("command")
        )
        
    def _open_manage_window(self, client: dict) -> None:
        """
        Ανοίγει παράθυρο διαχείρισης για συγκεκριμένο client.
        """

        client_code = client.get("client_code", "")

        if not client_code:
            return

        existing_window = self.manage_windows.get(client_code)

        if existing_window and existing_window.winfo_exists():
            existing_window.focus()
            return

        window = ClientManageWindow(
            self,
            client=client,
            on_rename_callback=self._rename_client,
            on_terminal_command_callback=self._send_terminal_command
        )

        self.manage_windows[client_code] = window