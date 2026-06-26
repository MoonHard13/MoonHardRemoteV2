import logging
import time
import uuid
from typing import Any

import customtkinter as ctk

from app.config import DashboardConfig
from app.ui.theme import COLORS, FONTS, SPACING, card_style
from app.views.clients_view import ClientsView
from app.websocket_client import DashboardWebSocketClient
from app.views.client_manage_window import ClientManageWindow
from app.views.bulk_update_progress_window import BulkUpdateProgressWindow


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
        self.bulk_update_active: bool = False
        self.bulk_update_states: dict[str, dict[str, Any]] = {}
        self.bulk_update_window: BulkUpdateProgressWindow | None = None
        self.bulk_update_max_retries: int = 2
        self.bulk_update_stuck_seconds: int = 180
        self.bulk_update_watchdog_job = None
        self.bulk_update_max_parallel_downloads: int = 5
        self.bulk_update_active_downloads: set[str] = set()
        self.bulk_update_download_queue: list[str] = []
        self.clients_auto_refresh_interval_ms: int = 600000
        self.clients_auto_refresh_job = None
                
        self.title(self.config_data.app_name)
        self.geometry("1100x700")
        self.minsize(900, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.configure(fg_color=COLORS.background)

        self._build_ui()
        self._start_websocket()
        self._schedule_clients_auto_refresh()

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
            on_manage_callback=self._open_manage_window,
            on_delete_callback=self._delete_client,
            on_refresh_callback=self._refresh_clients,
            on_bulk_update_callback=self._bulk_update_clients,
            on_group_callback=self._update_client_group,
            on_create_group_callback=self._create_client_group,
            on_rename_group_callback=self._rename_client_group,
            on_delete_group_callback=self._delete_client_group
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
            self._update_open_manage_windows(clients)
            self._update_bulk_completion_from_clients_list(clients)

            if updated:
                logger.info("Dashboard clients list updated. Count: %s", len(clients))

        elif message_type == "dashboard_connected":
            logger.info("Dashboard connected. Requesting client groups.")
            self._request_client_groups()

        elif message_type == "rename_client_success":
            logger.info("Client renamed successfully.")

        elif message_type == "rename_client_error":
            logger.error("Client rename failed: %s", payload.get("message"))

        elif message_type == "client_groups_result":
            if payload.get("success"):
                groups = payload.get("groups", [])
                self.clients_view.update_groups(groups)
                logger.info("Client groups updated. Count: %s", len(groups))
            else:
                logger.error("Failed to load client groups: %s", payload.get("message"))

        elif message_type == "update_client_group_success":
            logger.info(
                "Client group updated successfully. client_code=%s",
                payload.get("client_code")
            )
            self._request_client_groups()
            self._refresh_clients()

        elif message_type == "update_client_group_error":
            logger.error(
                "Client group update failed for %s: %s",
                payload.get("client_code"),
                payload.get("message")
            )

        elif message_type == "create_client_group_success":
            logger.info(
                "Client group created successfully: %s",
                payload.get("group")
            )
            self._request_client_groups()
            self._refresh_clients()

        elif message_type == "create_client_group_error":
            logger.error(
                "Client group create failed: %s",
                payload.get("message")
            )

        elif message_type == "rename_client_group_success":
            logger.info(
                "Client group renamed successfully: %s",
                payload.get("group")
            )
            self._request_client_groups()
            self._refresh_clients()

        elif message_type == "rename_client_group_error":
            logger.error(
                "Client group rename failed for %s: %s",
                payload.get("group_id"),
                payload.get("message")
            )

        elif message_type == "delete_client_group_success":
            logger.info(
                "Client group deleted successfully: %s",
                payload.get("result")
            )
            self._request_client_groups()
            self._refresh_clients()

        elif message_type == "delete_client_group_error":
            logger.error(
                "Client group delete failed for %s: %s",
                payload.get("group_id"),
                payload.get("message")
            )

        elif message_type == "terminal_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_terminal_result(payload)

        elif message_type == "delete_client_success":
            logger.info("Client deleted successfully: %s", payload.get("client_code"))

        elif message_type == "delete_client_error":
            logger.error(
                "Client delete failed for %s: %s",
                payload.get("client_code"),
                payload.get("message")
            )

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

        elif message_type == "senario_prosorinon_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_senario_prosorinon_result(payload)

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

            self._handle_bulk_update_check_result(payload)

        elif message_type == "client_update_download_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_download_result(payload)

            self._handle_bulk_update_download_result(payload)

        elif message_type == "client_update_extract_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_extract_result(payload)

            self._handle_bulk_update_extract_result(payload)

        elif message_type == "client_update_apply_result":
            client_code = payload.get("client_code", "")
            manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                manage_window.handle_client_update_apply_result(payload)

            self._handle_bulk_update_apply_result(payload)

    def _update_open_manage_windows(self, clients: list[dict]) -> None:
        """
        Ενημερώνει όλα τα ανοιχτά Manage windows με φρέσκα στοιχεία client.
        """

        clients_by_code = {
            str(client.get("client_code", "")): client
            for client in clients
        }

        for client_code, manage_window in list(self.manage_windows.items()):
            if not manage_window or not manage_window.winfo_exists():
                self.manage_windows.pop(client_code, None)
                continue

            fresh_client = clients_by_code.get(client_code)

            if fresh_client:
                manage_window.update_client_data(fresh_client)

    def _set_connection_status_threadsafe(self, status: str) -> None:
        """
        Μεταφέρει την αλλαγή κατάστασης σύνδεσης στο κύριο GUI thread.
        """

        self.after(0, lambda: self.status_label.configure(text=status))

    def on_close(self) -> None:
        """
        Κλείνει σωστά το dashboard.
        """

        if self.clients_auto_refresh_job:
            try:
                self.after_cancel(self.clients_auto_refresh_job)
            except Exception:
                pass
            self.clients_auto_refresh_job = None

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

    def _request_client_groups(self) -> None:
        """
        Ζητάει τη λίστα των client groups από τον server.
        """

        if not self.websocket_client:
            logger.warning("Cannot request client groups. WebSocket is not connected.")
            return

        self.websocket_client.send_message(
            {
                "type": "get_client_groups"
            }
        )

        logger.info("Client groups request sent.")

    def _update_client_group(self, client: dict, group_name: str) -> None:
        """
        Στέλνει αίτημα αλλαγής group για συγκεκριμένο client.
        """

        if not self.websocket_client:
            logger.warning("Cannot update client group. WebSocket is not connected.")
            return

        client_code = str(client.get("client_code", "")).strip()
        clean_group_name = group_name.strip()

        if not client_code:
            logger.warning("Cannot update client group. Missing client_code.")
            return

        if not clean_group_name:
            clean_group_name = "Ungrouped"

        self.websocket_client.send_message(
            {
                "type": "update_client_group",
                "client_code": client_code,
                "group_name": clean_group_name
            }
        )

        logger.info(
            "Update client group request sent. client_code=%s group_name=%s",
            client_code,
            clean_group_name
        )

    def _create_client_group(self, group_name: str) -> None:
        """
        Στέλνει αίτημα δημιουργίας client group.
        """

        if not self.websocket_client:
            logger.warning("Cannot create client group. WebSocket is not connected.")
            return

        clean_group_name = group_name.strip()

        if not clean_group_name:
            logger.warning("Cannot create client group. Empty group name.")
            return

        self.websocket_client.send_message(
            {
                "type": "create_client_group",
                "group_name": clean_group_name
            }
        )

        logger.info(
            "Create client group request sent. group_name=%s",
            clean_group_name
        )

    def _rename_client_group(self, group: dict, new_name: str) -> None:
        """
        Στέλνει αίτημα μετονομασίας client group.
        """

        if not self.websocket_client:
            logger.warning("Cannot rename client group. WebSocket is not connected.")
            return

        group_id = str(group.get("id", "")).strip()
        clean_new_name = new_name.strip()

        if not group_id:
            logger.warning("Cannot rename client group. Missing group_id.")
            return

        if not clean_new_name:
            logger.warning("Cannot rename client group. Empty new_name.")
            return

        self.websocket_client.send_message(
            {
                "type": "rename_client_group",
                "group_id": group_id,
                "new_name": clean_new_name
            }
        )

        logger.info(
            "Rename client group request sent. group_id=%s new_name=%s",
            group_id,
            clean_new_name
        )

    def _delete_client_group(self, group: dict) -> None:
        """
        Στέλνει αίτημα διαγραφής client group.
        """

        if not self.websocket_client:
            logger.warning("Cannot delete client group. WebSocket is not connected.")
            return

        group_id = str(group.get("id", "")).strip()

        if not group_id:
            logger.warning("Cannot delete client group. Missing group_id.")
            return

        self.websocket_client.send_message(
            {
                "type": "delete_client_group",
                "group_id": group_id
            }
        )

        logger.info(
            "Delete client group request sent. group_id=%s group_name=%s",
            group_id,
            group.get("name")
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

    def _send_senario_request(self, payload: dict) -> None:
        """
        Στέλνει Senario Prosorinon request στον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(payload)

        logger.info(
            "Senario Prosorinon request sent. client_code=%s bo_connection_id=%s",
            payload.get("client_code"),
            payload.get("bo_connection_id")
        )

    def _bulk_update_clients(self, clients: list[dict]) -> None:
        """
        Ξεκινά πλήρες bulk update για όλους τους online/connected clients.
        Εκτελεί αυτόματα Check → Download → Extract → Apply.
        """

        connected_clients = [
            client
            for client in clients
            if bool(client.get("ws_connected", False))
        ]

        if not connected_clients:
            logger.warning("Bulk update skipped. No connected clients found.")
            return

        confirm = ctk.CTkInputDialog(
            text=(
                f"Type UPDATE to start FULL bulk update for {len(connected_clients)} connected clients.\n\n"
                "This will automatically run:\n"
                "Check → Download → Extract → Apply\n\n"
                "Clients will restart one by one if update is available."
            ),
            title="Confirm Full Bulk Update"
        )

        answer = confirm.get_input()

        if answer != "UPDATE":
            logger.info("Bulk update cancelled by user.")
            return

        self.bulk_update_active = True
        self.bulk_update_states = {}
        self.bulk_update_active_downloads.clear()
        self.bulk_update_download_queue.clear()
        
        if self.bulk_update_window and self.bulk_update_window.winfo_exists():
            self.bulk_update_window.destroy()

        self.bulk_update_window = BulkUpdateProgressWindow(
            self,
            on_retry_callback=self._retry_bulk_update_clients
        )
        self.bulk_update_window.initialize_clients(connected_clients)

        logger.info("Full bulk update started for %s clients.", len(connected_clients))

        for index, client in enumerate(connected_clients):
            client_code = str(client.get("client_code", ""))

            if not client_code:
                continue

            self.bulk_update_states[client_code] = {
                "client": client,
                "stage": "queued",
                "error": "",
                "latest_version": "",
                "download_url": "",
                "sha256": "",
                "package_path": "",
                "extracted_path": "",
                "retry_count": 0,
                "updated_at": time.monotonic()
            }

            delay_ms = index * 2000

            self.after(
                delay_ms,
                lambda c=client: self._bulk_send_update_check(c)
            )
        self._schedule_bulk_update_watchdog()
        self._refresh_bulk_update_window()

    def _bulk_send_update_check(self, client: dict) -> None:
        """
        Στέλνει check update request σε έναν client για bulk update.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        client_code = str(client.get("client_code", ""))

        if not client_code:
            return

        request_id = str(uuid.uuid4())

        if client_code in self.bulk_update_states:
            self._set_bulk_update_state(
                client_code,
                "checking",
                extra_values={"check_request_id": request_id}
            )

        self.websocket_client.send_message(
            {
                "type": "client_update_check",
                "request_id": request_id,
                "client_code": client_code
            }
        )

        logger.info(
            "Bulk update check sent. client_code=%s request_id=%s",
            client_code,
            request_id
        )

    def _bulk_send_update_download(self, client_code: str) -> None:
        """
        Στέλνει download update request σε έναν client για bulk update.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        state = self.bulk_update_states.get(client_code)

        if not state:
            return

        request_id = str(uuid.uuid4())

        self._set_bulk_update_state(
            client_code,
            "downloading",
            extra_values={"download_request_id": request_id}
        )

        self.websocket_client.send_message(
            {
                "type": "client_update_download",
                "request_id": request_id,
                "client_code": client_code,
                "download_url": state.get("download_url", ""),
                "sha256": state.get("sha256", ""),
                "latest_version": state.get("latest_version", "")
            }
        )

        logger.info(
            "Bulk update download sent. client_code=%s request_id=%s",
            client_code,
            request_id
        )

    def _queue_bulk_update_download(self, client_code: str) -> None:
        """
        Βάζει client στην ουρά download ώστε να μην κατεβάζουν όλοι ταυτόχρονα.
        """

        if client_code not in self.bulk_update_states:
            return

        if client_code in self.bulk_update_active_downloads:
            return

        if client_code not in self.bulk_update_download_queue:
            self.bulk_update_download_queue.append(client_code)

        self._set_bulk_update_state(
            client_code,
            "waiting_download_slot"
        )

        logger.info(
            "Bulk update download queued. client_code=%s queue_size=%s active_downloads=%s",
            client_code,
            len(self.bulk_update_download_queue),
            len(self.bulk_update_active_downloads)
        )

        self._process_bulk_update_download_queue()

    def _process_bulk_update_download_queue(self) -> None:
        """
        Ξεκινά downloads από την ουρά μέχρι το επιτρεπτό όριο παράλληλων downloads.
        """

        while (
            self.bulk_update_download_queue
            and len(self.bulk_update_active_downloads) < self.bulk_update_max_parallel_downloads
        ):
            client_code = self.bulk_update_download_queue.pop(0)

            state = self.bulk_update_states.get(client_code)

            if not state:
                continue

            stage = str(state.get("stage", ""))

            if stage in ("completed", "up_to_date", "failed"):
                continue

            self.bulk_update_active_downloads.add(client_code)

            logger.info(
                "Bulk update download slot acquired. client_code=%s active_downloads=%s",
                client_code,
                len(self.bulk_update_active_downloads)
            )

            self._bulk_send_update_download(client_code)

    def _release_bulk_update_download_slot(self, client_code: str) -> None:
        """
        Ελευθερώνει download slot και ξεκινά τον επόμενο client από την ουρά.
        """

        if client_code in self.bulk_update_active_downloads:
            self.bulk_update_active_downloads.remove(client_code)

        logger.info(
            "Bulk update download slot released. client_code=%s active_downloads=%s queue_size=%s",
            client_code,
            len(self.bulk_update_active_downloads),
            len(self.bulk_update_download_queue)
        )

        self._process_bulk_update_download_queue()

    def _bulk_send_update_extract(self, client_code: str) -> None:
        """
        Στέλνει extract update request σε έναν client για bulk update.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        state = self.bulk_update_states.get(client_code)

        if not state:
            return

        request_id = str(uuid.uuid4())

        self._set_bulk_update_state(
            client_code,
            "extracting",
            extra_values={"extract_request_id": request_id}
        )

        self.websocket_client.send_message(
            {
                "type": "client_update_extract",
                "request_id": request_id,
                "client_code": client_code,
                "package_path": state.get("package_path", ""),
                "latest_version": state.get("latest_version", "")
            }
        )

        logger.info(
            "Bulk update extract sent. client_code=%s request_id=%s",
            client_code,
            request_id
        )

    def _bulk_send_update_apply(self, client_code: str) -> None:
        """
        Στέλνει apply update request σε έναν client για bulk update.
        """

        if not self.websocket_client:
            logger.warning("Dashboard WebSocket is not connected.")
            return

        state = self.bulk_update_states.get(client_code)

        if not state:
            return

        request_id = str(uuid.uuid4())

        self._set_bulk_update_state(
            client_code,
            "applying",
            extra_values={"apply_request_id": request_id}
        )

        self.websocket_client.send_message(
            {
                "type": "client_update_apply",
                "request_id": request_id,
                "client_code": client_code,
                "extracted_path": state.get("extracted_path", ""),
                "latest_version": state.get("latest_version", "")
            }
        )

        logger.info(
            "Bulk update apply sent. client_code=%s request_id=%s",
            client_code,
            request_id
        )

    def _set_bulk_update_state(
        self,
        client_code: str,
        stage: str,
        error: str = "",
        extra_values: dict[str, Any] | None = None
    ) -> None:
        """
        Ενημερώνει κεντρικά την κατάσταση ενός bulk update client.
        """

        state = self.bulk_update_states.get(client_code)

        if not state:
            return

        state["stage"] = stage
        state["error"] = error
        state["updated_at"] = time.monotonic()

        if extra_values:
            state.update(extra_values)

        self._refresh_bulk_update_window()

    def _is_bulk_retryable_stage(self, stage: str) -> bool:
        """
        Ελέγχει αν ένα bulk update stage μπορεί να ξαναδοκιμαστεί.
        """

        return stage in {
            "failed",
            "stuck",
            "queued",
            "checking",
            "waiting_download_slot",
            "downloading",
            "extracting",
            "applying",
            "apply_started"
        }

    def _retry_bulk_update_clients(self, automatic: bool = False) -> None:
        """
        Κάνει retry μόνο clients που απέτυχαν, κόλλησαν ή δεν ολοκληρώθηκαν.
        Παραλείπει completed και up_to_date.
        """

        if not self.bulk_update_states:
            logger.info("Bulk retry skipped. No bulk update states found.")
            return

        retry_clients: list[dict] = []

        for client_code, state in self.bulk_update_states.items():
            stage = str(state.get("stage", ""))
            retry_count = int(state.get("retry_count", 0))

            if stage in ("completed", "up_to_date"):
                continue

            if not self._is_bulk_retryable_stage(stage):
                continue

            if retry_count >= self.bulk_update_max_retries:
                self._set_bulk_update_state(
                    client_code,
                    "failed",
                    error=f"Max retry limit reached ({self.bulk_update_max_retries})."
                )
                continue

            client = state.get("client")

            if isinstance(client, dict):
                retry_clients.append(client)

        if not retry_clients:
            logger.info("Bulk retry skipped. No retryable clients found.")
            self._refresh_bulk_update_window()
            return

        if not automatic:
            confirm = ctk.CTkInputDialog(
                text=(
                    f"Type RETRY to retry {len(retry_clients)} failed/stuck/not completed clients.\n\n"
                    "Completed and up-to-date clients will be skipped."
                ),
                title="Confirm Bulk Retry"
            )

            answer = confirm.get_input()

            if answer != "RETRY":
                logger.info("Bulk retry cancelled by user.")
                return

        self.bulk_update_active = True

        logger.info(
            "Bulk retry started. automatic=%s count=%s",
            automatic,
            len(retry_clients)
        )

        for index, client in enumerate(retry_clients):
            client_code = str(client.get("client_code", ""))

            if not client_code or client_code not in self.bulk_update_states:
                continue

            state = self.bulk_update_states[client_code]
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            state["error"] = ""
            state["latest_version"] = ""
            state["download_url"] = ""
            state["sha256"] = ""
            state["package_path"] = ""
            state["extracted_path"] = ""
            state["updated_at"] = time.monotonic()
            state["stage"] = "queued"

            delay_ms = index * 2000

            self.after(
                delay_ms,
                lambda c=client: self._bulk_send_update_check(c)
            )

        self._schedule_bulk_update_watchdog()
        self._refresh_bulk_update_window()

    def _handle_bulk_update_check_result(self, payload: dict[str, Any]) -> None:
        """
        Χειρίζεται check result για bulk update και προχωρά σε download αν χρειάζεται.
        """

        client_code = str(payload.get("client_code", ""))

        if not self.bulk_update_active or client_code not in self.bulk_update_states:
            return

        state = self.bulk_update_states[client_code]

        if not payload.get("success"):
            self._set_bulk_update_state(
                client_code,
                "failed",
                error=str(payload.get("error", "Unknown check error."))
            )

            logger.error(
                "Bulk update check failed. client_code=%s error=%s",
                client_code,
                state.get("error", "")
            )
            return

        if not payload.get("update_available", False):
            self._set_bulk_update_state(
                client_code,
                "up_to_date"
            )

            logger.info("Bulk update skipped. Client already up to date: %s", client_code)
            return

        self._set_bulk_update_state(
            client_code,
            "checking",
            extra_values={
                "latest_version": str(payload.get("latest_version", "")),
                "download_url": str(payload.get("download_url", "")),
                "sha256": str(payload.get("sha256", ""))
            }
        )

        state = self.bulk_update_states[client_code]

        if not state["download_url"] or not state["sha256"]:
            self._set_bulk_update_state(
                client_code,
                "failed",
                error="Missing download_url or sha256."
            )

            logger.error("Bulk update check missing data. client_code=%s", client_code)
            return

        self.after(
            1000,
            lambda code=client_code: self._queue_bulk_update_download(code)
        )
        
        self._log_bulk_update_summary()

    def _handle_bulk_update_download_result(self, payload: dict[str, Any]) -> None:
        """
        Χειρίζεται download result για bulk update και προχωρά σε extract.
        """

        client_code = str(payload.get("client_code", ""))

        if not self.bulk_update_active or client_code not in self.bulk_update_states:
            return

        self._release_bulk_update_download_slot(client_code)

        state = self.bulk_update_states[client_code]

        if not payload.get("success"):
            self._set_bulk_update_state(
                client_code,
                "failed",
                error=str(payload.get("error", "Unknown download error."))
            )

            logger.error(
                "Bulk update download failed. client_code=%s error=%s",
                client_code,
                state.get("error", "")
            )
            return

        saved_path = str(payload.get("saved_path", ""))

        if not saved_path:
            self._set_bulk_update_state(
                client_code,
                "failed",
                error="Missing saved_path."
            )

            logger.error("Bulk update download missing saved_path. client_code=%s", client_code)
            return

        self._set_bulk_update_state(
            client_code,
            "downloading",
            extra_values={
                "package_path": saved_path
            }
        )

        self.after(
            1000,
            lambda code=client_code: self._bulk_send_update_extract(code)
        )

        self._log_bulk_update_summary()

    def _handle_bulk_update_extract_result(self, payload: dict[str, Any]) -> None:
        """
        Χειρίζεται extract result για bulk update και προχωρά σε apply.
        """

        client_code = str(payload.get("client_code", ""))

        if not self.bulk_update_active or client_code not in self.bulk_update_states:
            return

        state = self.bulk_update_states[client_code]

        if not payload.get("success"):
            self._set_bulk_update_state(
                client_code,
                "failed",
                error=str(payload.get("error", "Unknown extract error."))
            )

            logger.error(
                "Bulk update extract failed. client_code=%s error=%s",
                client_code,
                state.get("error", "")
            )
            return

        extracted_path = str(payload.get("extracted_path", ""))

        if not extracted_path:
            self._set_bulk_update_state(
                client_code,
                "failed",
                error="Missing extracted_path."
            )

            logger.error("Bulk update extract missing extracted_path. client_code=%s", client_code)
            return

        self._set_bulk_update_state(
            client_code,
            "extracting",
            extra_values={
                "extracted_path": extracted_path
            }
        )

        self.after(
            1000,
            lambda code=client_code: self._bulk_send_update_apply(code)
        )

        self._log_bulk_update_summary()

    def _handle_bulk_update_apply_result(self, payload: dict[str, Any]) -> None:
        """
        Χειρίζεται apply result για bulk update.
        """

        client_code = str(payload.get("client_code", ""))

        if not self.bulk_update_active or client_code not in self.bulk_update_states:
            return

        state = self.bulk_update_states[client_code]

        if not payload.get("success"):
            self._set_bulk_update_state(
                client_code,
                "failed",
                error=str(payload.get("error", "Unknown apply error."))
            )

            logger.error(
                "Bulk update apply failed. client_code=%s error=%s",
                client_code,
                state.get("error", "")
            )
            return

        self._set_bulk_update_state(
            client_code,
            "apply_started"
        )

        logger.info(
            "Bulk update apply started. Waiting for reconnect. client_code=%s latest_version=%s",
            client_code,
            state.get("latest_version", "")
        )

        self._log_bulk_update_summary()

    def _update_bulk_completion_from_clients_list(self, clients: list[dict]) -> None:
        """
        Ελέγχει από τη φρέσκια λίστα clients ποιοι bulk update clients ολοκληρώθηκαν.
        """

        if not self.bulk_update_active:
            return

        clients_by_code = {
            str(client.get("client_code", "")): client
            for client in clients
        }

        for client_code, state in self.bulk_update_states.items():
            if state.get("stage") not in ("apply_started", "applying"):
                continue

            client = clients_by_code.get(client_code)

            if not client:
                continue

            ws_connected = bool(client.get("ws_connected", False))
            app_version = str(client.get("app_version", ""))
            latest_version = str(state.get("latest_version", ""))

            if ws_connected and latest_version and app_version == latest_version:
                self._set_bulk_update_state(
                    client_code,
                    "completed"
                )

                logger.info(
                    "Bulk update completed. client_code=%s version=%s",
                    client_code,
                    app_version
                )

        self._log_bulk_update_summary()

    def _log_bulk_update_summary(self) -> None:
        """
        Γράφει συνοπτική κατάσταση bulk update στα logs.
        """

        if not self.bulk_update_states:
            return

        summary: dict[str, int] = {}

        for state in self.bulk_update_states.values():
            stage = str(state.get("stage", "unknown"))
            summary[stage] = summary.get(stage, 0) + 1

        completed = summary.get("completed", 0)
        up_to_date = summary.get("up_to_date", 0)
        failed = summary.get("failed", 0) + summary.get("stuck", 0)

        active_stages = {
            "queued",
            "checking",
            "waiting_download_slot",
            "downloading",
            "extracting",
            "applying",
            "apply_started"
        }

        still_waiting = sum(
            summary.get(stage, 0)
            for stage in active_stages
        )

        logger.info(
            "Bulk update summary: completed=%s up_to_date=%s failed_or_stuck=%s still_waiting=%s raw=%s",
            completed,
            up_to_date,
            failed,
            still_waiting,
            summary
        )

        still_running = still_waiting > 0

        if not still_running:
            retryable_exists = any(
                self._is_bulk_retryable_stage(str(state.get("stage", "")))
                and str(state.get("stage", "")) not in ("completed", "up_to_date")
                and int(state.get("retry_count", 0)) < self.bulk_update_max_retries
                for state in self.bulk_update_states.values()
            )

            if retryable_exists:
                self._auto_retry_bulk_update_if_needed()
                return

            self.bulk_update_active = False

            if self.bulk_update_watchdog_job:
                try:
                    self.after_cancel(self.bulk_update_watchdog_job)
                except Exception:
                    pass

                self.bulk_update_watchdog_job = None

            logger.info("Bulk update finished.")

    def _refresh_bulk_update_window(self) -> None:
        """
        Ανανεώνει το progress window του bulk update.
        """

        if (
            self.bulk_update_window
            and self.bulk_update_window.winfo_exists()
        ):
            self.bulk_update_window.update_states(self.bulk_update_states)

    def _schedule_bulk_update_watchdog(self) -> None:
        """
        Ξεκινά watchdog που εντοπίζει stuck bulk update clients.
        """

        if self.bulk_update_watchdog_job:
            try:
                self.after_cancel(self.bulk_update_watchdog_job)
            except Exception:
                pass

            self.bulk_update_watchdog_job = None

        self.bulk_update_watchdog_job = self.after(
            30000,
            self._bulk_update_watchdog_tick
        )

    def _bulk_update_watchdog_tick(self) -> None:
        """
        Ελέγχει αν κάποιο bulk update stage έχει κολλήσει.
        """

        self.bulk_update_watchdog_job = None

        if not self.bulk_update_active:
            return

        now = time.monotonic()
        changed = False

        active_stages = {
            "queued",
            "checking",
            "downloading",
            "extracting",
            "applying",
            "apply_started"
        }

        for client_code, state in self.bulk_update_states.items():
            stage = str(state.get("stage", ""))
            updated_at = float(state.get("updated_at", now))

            if stage not in active_stages:
                continue

            elapsed_seconds = now - updated_at

            if elapsed_seconds >= self.bulk_update_stuck_seconds:
                state["stage"] = "stuck"
                state["error"] = (
                    f"Stage '{stage}' timed out after {int(elapsed_seconds)} seconds."
                )
                state["updated_at"] = now
                changed = True

                logger.warning(
                    "Bulk update client marked as stuck. client_code=%s stage=%s elapsed=%s",
                    client_code,
                    stage,
                    int(elapsed_seconds)
                )

        if changed:
            self._refresh_bulk_update_window()
            self._auto_retry_bulk_update_if_needed()

        self._log_bulk_update_summary()

        if self.bulk_update_active:
            self._schedule_bulk_update_watchdog()

    def _auto_retry_bulk_update_if_needed(self) -> None:
        """
        Κάνει auto-retry σε retryable clients μέχρι το επιτρεπτό όριο.
        """

        retryable_exists = False

        for state in self.bulk_update_states.values():
            stage = str(state.get("stage", ""))
            retry_count = int(state.get("retry_count", 0))

            if (
                self._is_bulk_retryable_stage(stage)
                and stage not in ("completed", "up_to_date")
                and retry_count < self.bulk_update_max_retries
            ):
                retryable_exists = True
                break

        if retryable_exists:
            self._retry_bulk_update_clients(automatic=True)
        
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
            on_update_request_callback=self._send_update_request,
            on_senario_request_callback=self._send_senario_request
        )

        self.manage_windows[client_code] = window
        open_window_count = len(
            [
                manage_window
                for manage_window in self.manage_windows.values()
                if manage_window and manage_window.winfo_exists()
            ]
        )

        offset = min(open_window_count * 30, 240)
        window.geometry(f"1000x700+{120 + offset}+{80 + offset}")

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
    
    def _delete_client(self, client: dict) -> None:
        """
        Στέλνει αίτημα διαγραφής client στον server.
        """

        client_code = client.get("client_code", "")

        if not client_code:
            return

        if self.websocket_client:
            self.websocket_client.send_message(
                {
                    "type": "delete_client",
                    "client_code": client_code
                }
            )
            
    def _refresh_clients(self) -> None:
        """
        Ζητάει φρέσκια λίστα clients από τον server.
        """

        if self.websocket_client:
            self.websocket_client.send_message(
                {
                    "type": "refresh_clients"
                }
            )
            
    def _schedule_clients_auto_refresh(self) -> None:
        """
        Κάνει auto refresh τη λίστα clients κάθε 10 λεπτά.
        Το manual refresh εξακολουθεί να δουλεύει άμεσα.
        """
        if self.clients_auto_refresh_job:
            try:
                self.after_cancel(self.clients_auto_refresh_job)
            except Exception:
                pass

            self.clients_auto_refresh_job = None

        self.clients_auto_refresh_job = self.after(
            self.clients_auto_refresh_interval_ms,
            self._clients_auto_refresh_tick
        )

    def _clients_auto_refresh_tick(self) -> None:
        """
        Εκτελεί ένα refresh_clients και ξαναπρογραμματίζει το επόμενο.
        """
        self.clients_auto_refresh_job = None

        self._refresh_clients()
        self._schedule_clients_auto_refresh()