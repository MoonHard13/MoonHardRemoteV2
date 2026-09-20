from typing import Callable, Any

import customtkinter as ctk

from app.appsettings_presenter import AppSettingsPresenter
from app.ui.theme import COLORS, FONTS, SPACING
from app.views.manage.provider_tab import ProviderTab
from app.views.manage.overview_tab import OverviewTab
from app.views.manage.terminal_tab import TerminalTab
from app.views.manage.appsettings_tab import AppSettingsTab
from app.views.manage.database_tab import DatabaseTab
from app.views.manage.sql_tab import SqlTab
from app.views.manage.services_tab import ServicesTab
from app.views.manage.processes_tab import ProcessesTab
from app.views.manage.updates_tab import UpdatesTab
from app.views.manage.senario_prosorinon_tab import SenarioProsorinonTab


class ClientManageWindow(ctk.CTkToplevel):
    """
    Παράθυρο διαχείρισης ενός συγκεκριμένου client.
    Οι λειτουργίες είναι οργανωμένες σε tabs.
    """

    TAB_NAMES = (
        "Overview",
        "Terminal",
        "AppSettings",
        "SSMS",
        "Database",
        "Provider",
        "Services",
        "Processes",
        "Updates",
        "Senario Prosorinon"
    )

    def __init__(
        self,
        parent,
        client: dict,
        on_rename_callback: Callable[[str, str], None] | None = None,
        on_reset_token_callback: Callable[[str], None] | None = None,
        on_terminal_command_callback: Callable[[dict], None] | None = None,
        on_terminal_autocomplete_callback: Callable[[dict], None] | None = None,
        on_sql_execute_callback: Callable[[dict], None] | None = None,
        on_database_request_callback: Callable[[dict], None] | None = None,
        on_backup_request_callback: Callable[[dict], bool | None] | None = None,
        on_provider_request_callback: Callable[[dict], None] | None = None,
        on_services_request_callback: Callable[[dict], None] | None = None,
        on_service_action_callback: Callable[[dict], None] | None = None,
        on_processes_request_callback: Callable[[dict], None] | None = None,
        on_process_action_callback: Callable[[dict], None] | None = None,
        on_update_request_callback: Callable[[dict], None] | None = None,
        on_senario_request_callback: Callable[[dict], None] | None = None
        
    ) -> None:
        """
        Δημιουργεί το παράθυρο διαχείρισης client.
        """

        super().__init__(parent)

        self.client = client
        self.on_rename_callback = on_rename_callback
        self.on_reset_token_callback = on_reset_token_callback
        self.on_terminal_command_callback = on_terminal_command_callback
        self.on_terminal_autocomplete_callback = on_terminal_autocomplete_callback
        self.on_sql_execute_callback = on_sql_execute_callback
        self.on_database_request_callback = on_database_request_callback
        self.on_backup_request_callback = on_backup_request_callback

        self.client_code = client.get("client_code", "")
        self.appsettings_data: dict = {}
        self.bo_connections: list[dict] = []
        self.selected_bo_connection_id: int = 1
        self.on_provider_request_callback = on_provider_request_callback
        self.on_services_request_callback = on_services_request_callback
        self.on_service_action_callback = on_service_action_callback
        self.on_processes_request_callback = on_processes_request_callback
        self.on_process_action_callback = on_process_action_callback
        self.on_update_request_callback = on_update_request_callback
        self.on_senario_request_callback = on_senario_request_callback

        self.title(f"Manage Client - {client.get('display_name') or client.get('pc_name')}")
        self.geometry("1000x700")
        self.minsize(900, 600)
        # Δεν χρησιμοποιούμε grab_set() ή transient(), ώστε κάθε Manage window
        # να είναι κανονικό ανεξάρτητο παράθυρο με minimize/maximize.
        self.resizable(True, True)

        self.configure(fg_color=COLORS.background)

        self._build_ui()

        # Φέρνουμε το παράθυρο μπροστά χωρίς να μπλοκάρουμε το dashboard.
        self.after(100, self._bring_to_front)

    def _bring_to_front(self) -> None:
        """
        Φέρνει το Manage window μπροστά χωρίς να το κάνει modal.
        """

        try:
            self.lift()
            self.focus_force()

            # Μικρό topmost toggle για να έρθει σίγουρα μπροστά στα Windows.
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))

        except Exception:
            pass

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό UI με tabs.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(
            self,
            corner_radius=SPACING.small_radius,
            border_width=1,
            border_color=COLORS.border_soft,
            fg_color=COLORS.surface,
            segmented_button_fg_color=COLORS.background,
            segmented_button_selected_color=COLORS.accent_soft,
            segmented_button_selected_hover_color=COLORS.accent_soft,
            segmented_button_unselected_color=COLORS.surface_light,
            segmented_button_unselected_hover_color=COLORS.surface_hover,
            segmented_button_font=FONTS.body_bold,
            text_color=COLORS.text_primary,
            anchor="w"
        )
        self.tabs.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=(8, SPACING.window_padding),
            sticky="nsew"
        )

        self.overview_tab = self.tabs.add("Overview")
        self.terminal_tab = self.tabs.add("Terminal")
        self.appsettings_tab = self.tabs.add("AppSettings")

        self.overview_tab.grid_columnconfigure(0, weight=1)
        self.overview_tab.grid_rowconfigure(0, weight=1)
        self.terminal_tab.grid_columnconfigure(0, weight=1)
        self.terminal_tab.grid_rowconfigure(0, weight=1)
        self.appsettings_tab.grid_columnconfigure(0, weight=1)
        self.appsettings_tab.grid_rowconfigure(0, weight=1)
        self.sql_tab = self.tabs.add("SSMS")
        self.sql_tab.grid_columnconfigure(0, weight=1)
        self.sql_tab.grid_rowconfigure(0, weight=1)
        self.database_tab = self.tabs.add("Database")
        self.database_tab.grid_columnconfigure(0, weight=1)
        self.database_tab.grid_rowconfigure(0, weight=1)
        self.provider_tab = self.tabs.add("Provider")
        self.provider_tab.grid_columnconfigure(0, weight=1)
        self.provider_tab.grid_rowconfigure(0, weight=1)
        self.services_tab = self.tabs.add("Services")
        self.services_tab.grid_columnconfigure(0, weight=1)
        self.services_tab.grid_rowconfigure(0, weight=1)
        self.processes_tab = self.tabs.add("Processes")
        self.processes_tab.grid_columnconfigure(0, weight=1)
        self.processes_tab.grid_rowconfigure(0, weight=1)
        self.updates_tab = self.tabs.add("Updates")
        self.updates_tab.grid_columnconfigure(0, weight=1)
        self.updates_tab.grid_rowconfigure(0, weight=1)
        self.senario_prosorinon_tab = self.tabs.add("Senario Prosorinon")
        self.senario_prosorinon_tab.grid_columnconfigure(0, weight=1)
        self.senario_prosorinon_tab.grid_rowconfigure(0, weight=1)

        self._style_tab_navigation()
        self._bind_tab_shortcuts()

        self._build_overview_tab()
        self._build_terminal_tab()
        self._build_appsettings_tab()
        self._build_sql_tab()
        self._build_database_tab()
        self._build_provider_tab()
        self._build_services_tab()
        self._build_processes_tab()
        self._build_updates_tab()
        self._build_senario_prosorinon_tab()

    def _style_tab_navigation(self) -> None:
        """Μετατρέπει το default segmented control σε πλήρες navigation bar."""

        navigation = self.tabs._segmented_button
        navigation.configure(
            height=42,
            corner_radius=SPACING.small_radius,
            border_width=0,
            dynamic_resizing=False,
            font=FONTS.body_bold
        )
        navigation.grid_configure(
            padx=SPACING.small_radius,
            pady=(0, 4),
            sticky="ew"
        )

        for column, (tab_name, button) in enumerate(
            navigation._buttons_dict.items()
        ):
            button.configure(
                height=42,
                border_spacing=8,
                font=FONTS.body_bold
            )
            navigation.grid_columnconfigure(
                column,
                weight=2 if tab_name in {"AppSettings", "Senario Prosorinon"} else 1
            )

    def _bind_tab_shortcuts(self) -> None:
        """Συνδέει Alt+1 έως Alt+0 με τα tabs του Manage window."""

        shortcut_keys = tuple(str(index) for index in range(1, 10)) + ("0",)
        for key, tab_name in zip(shortcut_keys, self.TAB_NAMES):
            self.bind(
                f"<Alt-Key-{key}>",
                lambda _event, name=tab_name: self._select_tab(name)
            )

    def _select_tab(self, tab_name: str) -> str:
        """Ενεργοποιεί tab από navigation shortcut."""

        self.tabs.set(tab_name)
        return "break"
        
    def update_client_data(self, client: dict) -> None:
        """
        Ενημερώνει άμεσα τα στοιχεία του ανοιχτού Manage window.
        """

        if not client:
            return

        self.client = client

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "—"
        status = self.client.get("status", "-")
        self.title(f"Manage Client - {display_name}")

        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.set_online(status == "online")

        if hasattr(self, "updates_tab_view"):
            self.updates_tab_view.update_client_state(self.client)

        if hasattr(self, "overview_tab_view"):
            self.overview_tab_view.update_client_data(self.client)

    def _build_overview_tab(self) -> None:
        """
        Δημιουργεί το Overview tab μέσω ξεχωριστού OverviewTab component.
        """

        self.overview_tab_view = OverviewTab(
            self.overview_tab,
            client=self.client,
            on_rename_callback=self.on_rename_callback,
            on_reset_token_callback=self.on_reset_token_callback
        )
        self.overview_tab_view.grid(row=0, column=0, sticky="nsew")

    def _build_terminal_tab(self) -> None:
        """
        Δημιουργεί το Terminal tab μέσω ξεχωριστού TerminalTab component.
        """

        self.terminal_tab_view = TerminalTab(
            self.terminal_tab,
            client_code=self.client_code,
            on_terminal_command_callback=self.on_terminal_command_callback,
            on_terminal_autocomplete_callback=self.on_terminal_autocomplete_callback,
            client_label=" • ".join(str(value) for value in (self.client.get("pc_name"), self.client.get("username"), self.client_code) if value)
        )
        self.terminal_tab_view.grid(row=0, column=0, sticky="nsew")

    def _build_services_tab(self) -> None:
        """
        Δημιουργεί το Services tab μέσω ξεχωριστού ServicesTab component.
        """

        self.services_tab_view = ServicesTab(
            self.services_tab,
            client_code=self.client_code,
            on_services_request_callback=self.on_services_request_callback,
            on_service_action_callback=self.on_service_action_callback
        )
        self.services_tab_view.grid(row=0, column=0, sticky="nsew")

    def _build_processes_tab(self) -> None:
        """
        Δημιουργεί το Processes tab μέσω ξεχωριστού ProcessesTab component.
        """

        self.processes_tab_view = ProcessesTab(
            self.processes_tab,
            client_code=self.client_code,
            on_processes_request_callback=self.on_processes_request_callback,
            on_process_action_callback=self.on_process_action_callback
        )
        self.processes_tab_view.grid(row=0, column=0, sticky="nsew")

    def _build_updates_tab(self) -> None:
        """
        Δημιουργεί το Updates tab μέσω ξεχωριστού UpdatesTab component.
        """

        self.updates_tab_view = UpdatesTab(
            self.updates_tab,
            client_code=self.client_code,
            on_update_request_callback=self.on_update_request_callback
        )
        self.updates_tab_view.grid(row=0, column=0, sticky="nsew")

    def _build_senario_prosorinon_tab(self) -> None:
        """
        Δημιουργεί το Senario Prosorinon tab.
        """

        self.senario_prosorinon_tab_view = SenarioProsorinonTab(
            self.senario_prosorinon_tab,
            client_code=self.client_code,
            get_bo_values_callback=self._build_bo_connection_values,
            get_selected_bo_id_callback=lambda: self.selected_bo_connection_id,
            on_senario_request_callback=self.on_senario_request_callback
        )
        self.senario_prosorinon_tab_view.grid(row=0, column=0, sticky="nsew")

    def handle_terminal_result(self, payload: dict) -> None:
        """
        Προωθεί terminal result στο TerminalTab.
        """

        if hasattr(self, "terminal_tab_view"):
            self.terminal_tab_view.handle_terminal_result(payload)

    def handle_client_token_reset_result(self, payload: dict) -> None:
        """
        Προωθεί reset token result στο OverviewTab.
        """

        if hasattr(self, "overview_tab_view"):
            self.overview_tab_view.handle_client_token_reset_result(payload)

    def handle_terminal_error(self, payload: dict) -> None:
        """
        Προωθεί terminal error στο TerminalTab.
        """

        if hasattr(self, "terminal_tab_view"):
            self.terminal_tab_view.handle_terminal_error(payload)


    def handle_terminal_autocomplete_result(self, payload: dict[str, Any]) -> None:
        """
        Προωθεί autocomplete result στο TerminalTab.
        """

        if hasattr(self, "terminal_tab_view"):
            self.terminal_tab_view.handle_terminal_autocomplete_result(payload)


    def handle_terminal_autocomplete_error(self, payload: dict[str, Any]) -> None:
        """
        Προωθεί autocomplete error στο TerminalTab.
        """

        if hasattr(self, "terminal_tab_view"):
            self.terminal_tab_view.handle_terminal_autocomplete_error(payload)

    def handle_services_get_result(self, payload: dict) -> None:
        """
        Προωθεί services result στο ServicesTab.
        """

        if hasattr(self, "services_tab_view"):
            self.services_tab_view.handle_services_result(payload)
 
    def handle_service_restart_result(self, payload: dict) -> None:
        """
        Προωθεί service restart result στο ServicesTab.
        """

        if hasattr(self, "services_tab_view"):
            self.services_tab_view.handle_service_restart_result(payload)

    def handle_service_start_result(self, payload: dict) -> None:
        """
        Προωθεί service start result στο ServicesTab.
        """

        if hasattr(self, "services_tab_view"):
            self.services_tab_view.handle_service_action_result(payload)


    def handle_service_stop_result(self, payload: dict) -> None:
        """
        Προωθεί service stop result στο ServicesTab.
        """

        if hasattr(self, "services_tab_view"):
            self.services_tab_view.handle_service_action_result(payload)

    def handle_processes_get_result(self, payload: dict) -> None:
        """
        Προωθεί processes result στο ProcessesTab.
        """

        if hasattr(self, "processes_tab_view"):
            self.processes_tab_view.handle_processes_result(payload)

    def handle_process_kill_result(self, payload: dict) -> None:
        """
        Προωθεί process kill result στο ProcessesTab.
        """

        if hasattr(self, "processes_tab_view"):
            self.processes_tab_view.handle_process_kill_result(payload)

    def handle_client_update_check_result(self, payload: dict) -> None:
        """
        Προωθεί update check result στο UpdatesTab.
        """

        if hasattr(self, "updates_tab_view"):
            self.updates_tab_view.handle_update_check_result(payload)

    def handle_client_update_download_result(self, payload: dict) -> None:
        """
        Προωθεί update download result στο UpdatesTab.
        """

        if hasattr(self, "updates_tab_view"):
            self.updates_tab_view.handle_update_download_result(payload)
        
    def _build_appsettings_tab(self) -> None:
        """
        Δημιουργεί το AppSettings tab μέσω ξεχωριστού AppSettingsTab component.
        """

        self.appsettings_tab_view = AppSettingsTab(
            self.appsettings_tab,
            on_bo_connection_selected=self._on_bo_connection_selected,
            on_refresh_callback=self._refresh_selected_bo_connection
        )
        self.appsettings_tab_view.grid(row=0, column=0, sticky="nsew")
        
    def handle_appsettings_result(self, payload: dict) -> None:
        """
        Λαμβάνει τα appsettings από τον server και ενημερώνει το AppSettings tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if not payload.get("success"):
            self.appsettings_data = {}
            self.bo_connections = []
            self._sync_bo_views()
            self._set_appsettings_text("Αποτυχία φόρτωσης AppSettings. Ανοίξτε ξανά τη διαχείριση για νέα ανάκτηση.")
            self.appsettings_tab_view.set_status("Αποτυχία φόρτωσης AppSettings.")
            return

        self.appsettings_data = AppSettingsPresenter.safe_data(payload.get("appsettings") or {})
        self.bo_connections = [item for item in self.appsettings_data.get("bo_connections", [])
                               if isinstance(item, dict)] if self.appsettings_data.get("file_found") else []
        available = {str(item.get("ID")) for item in self.bo_connections}
        if str(self.selected_bo_connection_id) not in available:
            requested = self.appsettings_data.get("selected_bo_connection_id")
            self.selected_bo_connection_id = requested if str(requested) in available else (
                self.bo_connections[0].get("ID") if self.bo_connections else 1
            )
        self._sync_bo_views()
        self._refresh_selected_bo_connection()

    def _sync_bo_views(self) -> None:
        """Συγχρονίζει λίστες και κοινή επιλογή χωρίς εκτέλεση SQL ή provider ενεργειών."""
        values = self._build_bo_connection_values()
        selected = self._find_bo_option_value(self.selected_bo_connection_id)
        self.appsettings_tab_view.set_bo_values(values, selected)
        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.set_bo_values(values, selected)
        if hasattr(self, "database_tab_view"):
            self.database_tab_view.refresh_bo_values()
        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.update_bo_values(values, selected)
        if hasattr(self, "senario_prosorinon_tab_view"):
            self.senario_prosorinon_tab_view.refresh_bo_values()

    def _refresh_selected_bo_connection(self) -> None:
        """
        Εμφανίζει τα στοιχεία του επιλεγμένου BOConnection.
        """

        self.appsettings_tab_view.set_data(
            self.appsettings_data or {}, self._get_selected_bo_connection()
        )

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
        
    def _build_bo_connection_values(self) -> list[str]:
        """
        Δημιουργεί τις επιλογές BOConnections για το dropdown.
        """

        values: list[str] = []

        for connection in self.bo_connections:
            connection_id = connection.get("ID")
            database_connection = connection.get("DatabaseConnection") or ""
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

        self._sync_bo_views()
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
            if str(connection.get("ID")) == str(self.selected_bo_connection_id):
                return connection

        return self.bo_connections[0] if self.bo_connections else {}

    def _set_appsettings_text(self, text: str) -> None:
        """
        Ενημερώνει το textbox του AppSettings tab.
        """

        if hasattr(self, "appsettings_tab_view"):
            self.appsettings_tab_view.set_text(text)
        
    def _build_sql_tab(self) -> None:
        """
        Δημιουργεί το SQL tab μέσω ξεχωριστού SqlTab component.
        """

        self.sql_tab_view = SqlTab(
            self.sql_tab,
            client_code=self.client_code,
            on_sql_execute_callback=self.on_sql_execute_callback,
            on_bo_selected_callback=self._on_sql_bo_selected,
            online=self.client.get("status", "online") == "online"
        )
        self.sql_tab_view.grid(row=0, column=0, sticky="nsew")
        
    def _on_sql_bo_selected(self, selected_value: str) -> None:
        """Συγχρονίζει την επιλογή SSMS με το AppSettings και τις λοιπές προβολές."""
        self._on_bo_connection_selected(selected_value)

    def handle_sql_result(self, payload: dict) -> None:
        """
        Προωθεί SQL result στο SqlTab.
        """

        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.handle_sql_result(payload)


    def handle_sql_error(self, payload: dict) -> None:
        """
        Προωθεί SQL error στο SqlTab.
        """

        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.handle_sql_error(payload)


    def handle_sql_test_connection_result(self, payload: dict) -> None:
        """
        Προωθεί SQL test connection result στο SqlTab.
        """

        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.handle_sql_test_connection_result(payload)


    def handle_sql_cancel_result(self, payload: dict) -> None:
        """
        Προωθεί SQL cancel result στο SqlTab.
        """

        if hasattr(self, "sql_tab_view"):
            self.sql_tab_view.handle_sql_cancel_result(payload)

    def _build_database_tab(self) -> None:
        """Δημιουργεί το Database tab ως ανεξάρτητο modular component."""

        self.database_tab_view = DatabaseTab(
            self.database_tab,
            client_code=self.client_code,
            get_bo_values_callback=self._build_bo_connection_values,
            get_selected_bo_id_callback=lambda: self.selected_bo_connection_id,
            on_bo_selected_callback=self._on_database_bo_selected,
            on_database_request_callback=self.on_database_request_callback,
            on_backup_request_callback=self.on_backup_request_callback,
        )
        self.database_tab_view.grid(row=0, column=0, sticky="nsew")

    def _on_database_bo_selected(self, selected_value: str) -> None:
        """Συγχρονίζει την επιλογή Database με το AppSettings και τις λοιπές προβολές."""
        self._on_bo_connection_selected(selected_value)

    def handle_database_action_result(self, payload: dict) -> None:
        """Προωθεί database action result στο DatabaseTab."""

        if payload.get("client_code") != self.client_code:
            return
        if hasattr(self, "database_tab_view"):
            self.database_tab_view.handle_result(payload)

    def handle_database_action_progress(self, payload: dict) -> None:
        """Προωθεί live rebuild progress στο DatabaseTab."""

        if payload.get("client_code") != self.client_code:
            return
        if hasattr(self, "database_tab_view"):
            self.database_tab_view.handle_progress(payload)

    def handle_backup_result(self, payload: dict) -> None:
        """Προωθεί backup result στο Database tab του σωστού client."""

        if payload.get("client_code") != self.client_code:
            return
        if hasattr(self, "database_tab_view"):
            self.database_tab_view.handle_backup_result(payload)

    def handle_backup_progress(self, payload: dict) -> None:
        """Προωθεί live backup progress στο Backup Manager."""

        if payload.get("client_code") != self.client_code:
            return
        if hasattr(self, "database_tab_view"):
            self.database_tab_view.handle_backup_progress(payload)

    def _build_provider_tab(self) -> None:
        """
        Δημιουργεί το Provider tab ως ξεχωριστό modular component.
        """

        self.provider_tab_view = ProviderTab(
            parent=self.provider_tab,
            client_code=self.client_code,
            get_bo_values_callback=self._build_bo_connection_values,
            get_selected_bo_id_callback=lambda: self.selected_bo_connection_id,
            on_provider_request_callback=self.on_provider_request_callback
        )
        self.provider_tab_view.grid(row=0, column=0, sticky="nsew")
        
    def handle_provider_transmitted_result(self, payload: dict) -> None:
        """Προωθεί τα διαβιβασμένα στο ανεξάρτητο Provider component."""
        if payload.get("client_code") == self.client_code and hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_transmitted_result(payload)

    def handle_provider_search_invoices_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα αναζήτησης Provider/MUPT στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_search_result(payload)
            
    def handle_provider_send_invoices_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα αποστολής Provider/MUPT στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_send_result(payload)
            
    def handle_provider_get_errors_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα Provider/MyDATA errors στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_errors_result(payload)
            
    def handle_provider_get_payways_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα Provider payways στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_payways_result(payload)
            
    def handle_provider_delete_payway_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα διαγραφής Provider payway στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_delete_payway_result(payload)
            
    def handle_provider_delete_mydata_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα διαγραφής MyDATA responses στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_delete_mydata_result(payload)
            
    def handle_provider_get_note_types_result(self, payload: dict) -> None:
        """
        Προωθεί το αποτέλεσμα Note Types στο Provider tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.handle_note_types_result(payload)
            
    def handle_client_update_extract_result(self, payload: dict) -> None:
        """
        Προωθεί update extract result στο UpdatesTab.
        """

        if hasattr(self, "updates_tab_view"):
            self.updates_tab_view.handle_update_extract_result(payload)

    def handle_senario_prosorinon_result(self, payload: dict) -> None:
        """
        Προωθεί Senario Prosorinon result στο αντίστοιχο tab.
        """

        if payload.get("client_code") != self.client_code:
            return

        if hasattr(self, "senario_prosorinon_tab_view"):
            self.senario_prosorinon_tab_view.handle_result(payload)
            
    def handle_client_update_apply_result(self, payload: dict) -> None:
        """
        Προωθεί update apply result στο UpdatesTab.
        """

        if hasattr(self, "updates_tab_view"):
            self.updates_tab_view.handle_update_apply_result(payload)
