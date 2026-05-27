from typing import Callable, Any

import customtkinter as ctk

from app.ui.theme import COLORS, FONTS, SPACING, card_style
from app.views.manage.provider_tab import ProviderTab
from app.views.manage.overview_tab import OverviewTab
from app.views.manage.terminal_tab import TerminalTab
from app.views.manage.appsettings_tab import AppSettingsTab
from app.views.manage.sql_tab import SqlTab


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
        on_terminal_autocomplete_callback: Callable[[dict], None] | None = None,
        on_sql_execute_callback: Callable[[dict], None] | None = None,
        on_provider_request_callback: Callable[[dict], None] | None = None
        
    ) -> None:
        """
        Δημιουργεί το παράθυρο διαχείρισης client.
        """

        super().__init__(parent)

        self.client = client
        self.on_rename_callback = on_rename_callback
        self.on_terminal_command_callback = on_terminal_command_callback
        self.on_terminal_autocomplete_callback = on_terminal_autocomplete_callback
        self.on_sql_execute_callback = on_sql_execute_callback

        self.client_code = client.get("client_code", "")
        self.appsettings_data: dict = {}
        self.bo_connections: list[dict] = []
        self.selected_bo_connection_id: int = 1
        self.on_provider_request_callback = on_provider_request_callback

        self.title(f"Manage Client - {client.get('display_name') or client.get('pc_name')}")
        self.geometry("1000x700")
        self.minsize(900, 600)
        self.grab_set()
        self.configure(fg_color=COLORS.background)

        self._build_ui()

    def _build_ui(self) -> None:
        """
        Δημιουργεί το βασικό UI με tabs.
        """

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self.tabs = ctk.CTkTabview(
            self,
            corner_radius=SPACING.card_radius,
            fg_color=COLORS.surface,
            segmented_button_fg_color=COLORS.surface_light,
            segmented_button_selected_color=COLORS.accent,
            segmented_button_selected_hover_color=COLORS.accent_hover,
            segmented_button_unselected_color=COLORS.surface_light,
            segmented_button_unselected_hover_color=COLORS.surface_hover,
            text_color=COLORS.text_primary
        )
        self.tabs.grid(
            row=1,
            column=0,
            padx=SPACING.window_padding,
            pady=(0, SPACING.window_padding),
            sticky="nsew"
        )

        self.overview_tab = self.tabs.add("Overview")
        self.terminal_tab = self.tabs.add("Terminal")
        self.appsettings_tab = self.tabs.add("AppSettings")

        self.overview_tab.grid_columnconfigure(0, weight=1)
        self.overview_tab.grid_rowconfigure(0, weight=1)
        self.terminal_tab.grid_columnconfigure(0, weight=1)
        self.terminal_tab.grid_rowconfigure(1, weight=1)
        self.appsettings_tab.grid_columnconfigure(0, weight=1)
        self.appsettings_tab.grid_rowconfigure(1, weight=1)
        self.sql_tab = self.tabs.add("SQL")
        self.sql_tab.grid_columnconfigure(0, weight=1)
        self.sql_tab.grid_rowconfigure(2, weight=1)
        self.provider_tab = self.tabs.add("Provider")
        self.provider_tab.grid_columnconfigure(0, weight=1)
        self.provider_tab.grid_rowconfigure(0, weight=1)

        self._build_overview_tab()
        self._build_terminal_tab()
        self._build_appsettings_tab()
        self._build_sql_tab()
        self._build_provider_tab()
        
    def _build_header(self) -> None:
        """
        Δημιουργεί την κεφαλίδα του παραθύρου.
        """

        display_name = self.client.get("display_name") or self.client.get("pc_name") or "-"
        pc_name = self.client.get("pc_name", "-")
        username = self.client.get("username", "-")
        status = self.client.get("status", "-")

        header = ctk.CTkFrame(self, **card_style())
        header.grid(
            row=0,
            column=0,
            padx=SPACING.window_padding,
            pady=SPACING.window_padding,
            sticky="ew"
        )
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text=display_name,
            font=FONTS.title,
            text_color=COLORS.text_primary
        )
        title.grid(row=0, column=0, padx=18, pady=(14, 4), sticky="w")

        info = ctk.CTkLabel(
            header,
            text=f"PC: {pc_name} | User: {username} | Status: {status} | Code: {self.client_code}",
            font=FONTS.body,
            text_color=COLORS.text_secondary,
            anchor="w"
        )
        info.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="w")

    def _build_overview_tab(self) -> None:
        """
        Δημιουργεί το Overview tab μέσω ξεχωριστού OverviewTab component.
        """

        self.overview_tab_view = OverviewTab(
            self.overview_tab,
            client=self.client,
            on_rename_callback=self.on_rename_callback
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
            on_terminal_autocomplete_callback=self.on_terminal_autocomplete_callback
        )
        self.terminal_tab_view.grid(row=0, column=0, sticky="nsew")

    def handle_terminal_result(self, payload: dict) -> None:
        """
        Προωθεί terminal result στο TerminalTab.
        """

        if hasattr(self, "terminal_tab_view"):
            self.terminal_tab_view.handle_terminal_result(payload)


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
            message = payload.get("message", "Failed to load appsettings.")
            self._set_appsettings_text(f"ERROR: {message}")
            self.appsettings_tab_view.set_status("Failed to load appsettings.")
            return

        appsettings = payload.get("appsettings") or {}
        self.appsettings_data = appsettings

        file_found = appsettings.get("file_found", False)
        file_path = appsettings.get("file_path") or "-"
        last_read_at = appsettings.get("last_read_at") or "-"

        self.bo_connections = appsettings.get("bo_connections") or []
        self.selected_bo_connection_id = appsettings.get("selected_bo_connection_id") or 1

        if not file_found:
            self.appsettings_tab_view.set_status(
                "appsettings.production.json was not found on this client."
            )
            self._set_appsettings_text(
                f"File found: No\n"
                f"Path checked: {file_path}\n"
                f"Last read: {last_read_at}\n"
            )
            return

        bo_values = self._build_bo_connection_values()

        if bo_values:
            default_value = self._find_bo_option_value(self.selected_bo_connection_id)

            if default_value:
                self.appsettings_tab_view.set_bo_values(
                    values=bo_values,
                    selected_value=default_value
                )
            else:
                self.appsettings_tab_view.set_bo_values(
                    values=bo_values,
                    selected_value=bo_values[0]
                )
        else:
            self.appsettings_tab_view.set_bo_values(
                values=["No BOConnections"],
                selected_value="No BOConnections"
            )

        selected_bo_value = self.appsettings_tab_view.get_selected_bo_value()

        if hasattr(self, "sql_tab_view"):
            if bo_values:
                self.sql_tab_view.set_bo_values(
                    values=bo_values,
                    selected_value=selected_bo_value
                )
            else:
                self.sql_tab_view.set_bo_values(
                    values=["No BOConnections"],
                    selected_value="No BOConnections"
                )

        if hasattr(self, "provider_tab_view"):
            self.provider_tab_view.update_bo_values(
                bo_values=bo_values,
                selected_value=self.appsettings_tab_view.get_selected_bo_value()
            )

        self.appsettings_tab_view.set_status(
            f"Loaded from: {file_path} | Last read: {last_read_at}"
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
            on_bo_selected_callback=self._on_sql_bo_selected
        )
        self.sql_tab_view.grid(row=0, column=0, sticky="nsew")
        
    def _on_sql_bo_selected(self, selected_value: str) -> None:
        """
        Συγχρονίζει το επιλεγμένο BOConnection ID από το SQL tab.
        """

        connection_id = self._extract_bo_id_from_option(selected_value)

        if connection_id is not None:
            self.selected_bo_connection_id = connection_id


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