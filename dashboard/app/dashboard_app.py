import logging
from typing import Any

import customtkinter as ctk

from app.config import DashboardConfig
from app.ui.theme import COLORS, FONTS, SPACING, card_style
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

        self.configure(fg_color=COLORS.background)

        self._build_ui()
        self._start_websocket()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό layout του dashboard.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_frame = ctk.CTkFrame(self, **card_style())
        self.header_frame.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=(SPACING.window_padding, SPACING.large_gap),
            sticky="ew"
        )
        self.header_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            self.header_frame,
            text="MoonHard Remote v2",
            font=FONTS.title,
            text_color=COLORS.text_primary
        )
        title_label.grid(
            row=0,
            column=0,
            padx=SPACING.card_padding,
            pady=(SPACING.card_padding, 2),
            sticky="w"
        )

        subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Remote client control dashboard",
            font=FONTS.body,
            text_color=COLORS.text_secondary
        )
        subtitle_label.grid(
            row=1,
            column=0,
            padx=SPACING.card_padding,
            pady=(0, SPACING.card_padding),
            sticky="w"
        )

        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="Σύνδεση...",
            font=FONTS.body_bold,
            text_color=COLORS.accent
        )
        self.status_label.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=SPACING.card_padding,
            pady=SPACING.card_padding,
            sticky="e"
        )

        self.clients_view = ClientsView(
            self,
            on_manage_callback=self._open_manage_window
        )
        self.clients_view.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="nsew"
        )

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

            updated = self.clients_view.update_clients(clients)

            if updated:
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
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_terminal_autocomplete_result(payload)

        elif message_type == "terminal_autocomplete_error":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_terminal_autocomplete_error(payload)

            logger.error("Terminal autocomplete error: %s", payload.get("message"))
            
        elif message_type == "client_appsettings_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_appsettings_result(payload)
                
        elif message_type == "sql_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_sql_result(payload)

        elif message_type == "sql_error":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_sql_error(payload)

        elif message_type == "sql_test_connection_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_sql_test_connection_result(payload)

        elif message_type == "sql_cancel_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_sql_cancel_result(payload)
                
        elif message_type == "provider_search_invoices_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_search_invoices_result(payload)
                
        elif message_type == "provider_send_invoices_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_send_invoices_result(payload)
                
        elif message_type == "provider_get_errors_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_get_errors_result(payload)

        elif message_type == "provider_get_payways_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_get_payways_result(payload)
                
        elif message_type == "provider_delete_payway_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_delete_payway_result(payload)

        elif message_type == "provider_delete_mydata_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_delete_mydata_result(payload)

        elif message_type == "provider_get_note_types_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_provider_get_note_types_result(payload)

        elif message_type == "services_get_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_services_get_result(payload)

        elif message_type == "service_restart_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_service_restart_result(payload)

        elif message_type == "service_start_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_service_start_result(payload)

        elif message_type == "service_stop_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_service_stop_result(payload)

        elif message_type == "processes_get_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_processes_get_result(payload)

        elif message_type == "process_kill_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_process_kill_result(payload)

        elif message_type == "client_update_check_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_check_result(payload)

        elif message_type == "client_update_download_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_download_result(payload)

        elif message_type == "client_update_extract_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_extract_result(payload)

        elif message_type == "client_update_apply_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_apply_result(payload)

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

    def _send_terminal_autocomplete(self, payload: dict[str, Any]) -> None:
        """
        Στέλνει terminal autocomplete request στον server.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        self.websocket_client.send_message(payload)

        logger.info(
            "Terminal autocomplete sent. client_code=%s shell=%s command_text=%s",
            payload.get("client_code"),
            payload.get("shell"),
            payload.get("command_text")
        )

    def _send_processes_request(self, payload: dict) -> None:
        """
        Στέλνει processes request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)

    def _send_process_action(self, payload: dict) -> None:
        """
        Στέλνει process action request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)
 
    def _send_update_request(self, payload: dict) -> None:
        """
        Στέλνει update request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)
        
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
            on_terminal_command_callback=self._send_terminal_command,
            on_terminal_autocomplete_callback=self._send_terminal_autocomplete,
            on_sql_execute_callback=self._send_sql_execute,
            on_provider_request_callback=self._send_provider_request,
            on_services_request_callback=self._send_services_request,
            on_service_action_callback=self._send_service_action,
            on_processes_request_callback=self._send_processes_request,
            on_process_action_callback=self._send_process_action,
            on_update_request_callback=self._send_update_request
        )

        self.manage_windows[client_code] = window

        if self.websocket_client:
            self.websocket_client.send_message(
                {
                    "type": "get_client_appsettings",
                    "client_code": client_code
                }
            )
            
    def _send_sql_execute(self, payload: dict[str, Any]) -> None:
        """
        Στέλνει SQL execute request στον server.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        self.websocket_client.send_message(payload)

        logger.info(
            "SQL execute sent. client_code=%s bo_connection_id=%s",
            payload.get("client_code"),
            payload.get("bo_connection_id")
        )
        
    def _send_provider_request(self, payload: dict[str, Any]) -> None:
        """
        Στέλνει Provider/MUPT request στον server.
        Δεν αποθηκεύει τίποτα στη Supabase.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        self.websocket_client.send_message(payload)

        logger.info(
            "Provider request sent. type=%s client_code=%s",
            payload.get("type"),
            payload.get("client_code")
        )
        
    def _send_services_request(self, payload: dict) -> None:
        """
        Στέλνει services request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)
            
    def _send_service_action(self, payload: dict) -> None:
        """
        Στέλνει service action request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)
            
    def _create_clients_snapshot(self, clients: list[dict]) -> tuple:
        """
        Δημιουργεί σταθερό snapshot ώστε να αποφεύγονται άσκοπα redraws.
        """

        snapshot_items: list[tuple] = []

        for client in clients:
            snapshot_items.append(
                (
                    str(client.get("client_code", "")),
                    str(client.get("display_name", "")),
                    str(client.get("pc_name", "")),
                    str(client.get("username", "")),
                    str(client.get("status", "")),
                    str(client.get("app_version", "")),
                )
            )

        return tuple(sorted(snapshot_items))