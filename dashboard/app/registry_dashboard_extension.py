"""Registry Dashboard extension χωρίς αλλαγές στα μεγάλα dashboard modules."""

from __future__ import annotations

import logging
from typing import Any

from app.views.client_manage_window import ClientManageWindow as BaseClientManageWindow
from app.views.manage.registry_compare_center import RegistryCompareTab


logger = logging.getLogger(__name__)


class RegistryEnabledClientManageWindow(BaseClientManageWindow):
    """Προσθέτει Registry tab στο υπάρχον Manage window."""

    def __init__(self, parent, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)
        self._registry_parent_app = parent
        self._add_registry_tab()

    def _add_registry_tab(self) -> None:
        if hasattr(self, "registry_tab_view"):
            return

        self.registry_tab = self.tabs.add("Registry")
        self.registry_tab.grid_columnconfigure(0, weight=1)
        self.registry_tab.grid_rowconfigure(0, weight=1)
        self.registry_tab_view = RegistryCompareTab(
            self.registry_tab,
            client_code=self.client_code,
            on_registry_request_callback=self._send_registry_request,
            get_compare_clients_callback=self._get_registry_compare_clients,
        )
        self.registry_tab_view.grid(row=0, column=0, sticky="nsew")

        # Το ManageTabView έχει αριθμητικά shortcuts μέχρι 10 tabs.
        # Το Registry είναι 11ο τεχνικά, άρα αφαιρούμε το διπλό "0" και
        # το τοποθετούμε οπτικά αμέσως μετά το Provider.
        try:
            self.tabs.button("Registry").configure(text="Registry")
            order = list(self.tabs._tabs.keys())
            order.remove("Registry")
            provider_index = order.index("Provider") + 1
            order.insert(provider_index, "Registry")
            self.tabs._tabs = {name: self.tabs._tabs[name] for name in order}
            self.tabs._buttons = {name: self.tabs._buttons[name] for name in order}
            self.tabs._shortcuts = {name: self.tabs._shortcuts[name] for name in order}
            self.tabs._layout_navigation(force=True)
        except Exception:
            logger.exception("Could not reorder Registry tab navigation.")

    def _get_registry_compare_clients(self) -> list[dict[str, Any]]:
        clients_view = getattr(self._registry_parent_app, "clients_view", None)
        clients = getattr(clients_view, "clients", None)
        if not isinstance(clients, list):
            return []
        return [dict(client) for client in clients if isinstance(client, dict)]

    def _send_registry_request(self, payload: dict[str, Any]) -> bool:
        websocket_client = getattr(self._registry_parent_app, "websocket_client", None)
        if not websocket_client or not websocket_client.is_connected():
            return False

        request_id = str(payload.get("request_id") or "")
        routes = getattr(self._registry_parent_app, "_registry_request_routes", None)
        if not isinstance(routes, dict):
            routes = {}
            setattr(self._registry_parent_app, "_registry_request_routes", routes)
        if request_id:
            routes[request_id] = self

        sent = bool(websocket_client.send_message(payload))
        if not sent and request_id:
            routes.pop(request_id, None)
        return sent

    def handle_registry_result(self, payload: dict[str, Any]) -> None:
        if hasattr(self, "registry_tab_view"):
            self.registry_tab_view.handle_result(payload)

    def handle_registry_progress(self, payload: dict[str, Any]) -> None:
        if hasattr(self, "registry_tab_view"):
            self.registry_tab_view.handle_progress(payload)


def install_registry_dashboard_extension() -> None:
    """Patchάρει μόνο τα extension points που χρειάζεται το Registry feature."""

    import app.dashboard_app as dashboard_app_module

    if getattr(dashboard_app_module, "_registry_extension_installed", False):
        return

    dashboard_app_module._registry_extension_installed = True
    dashboard_app_module.ClientManageWindow = RegistryEnabledClientManageWindow

    app_class = dashboard_app_module.MoonHardDashboardApp
    original_handle = app_class._handle_websocket_message

    def handle_websocket_message(self, payload: dict[str, Any]) -> None:
        message_type = payload.get("type")
        if message_type in {"registry_result", "registry_progress"}:
            request_id = str(payload.get("request_id") or "")
            routes = getattr(self, "_registry_request_routes", None)
            if not isinstance(routes, dict):
                routes = {}
                setattr(self, "_registry_request_routes", routes)

            manage_window = routes.get(request_id)
            if not manage_window or not manage_window.winfo_exists():
                client_code = str(payload.get("client_code") or "")
                manage_window = self.manage_windows.get(client_code)

            if manage_window and manage_window.winfo_exists():
                if message_type == "registry_result" and hasattr(manage_window, "handle_registry_result"):
                    manage_window.handle_registry_result(payload)
                elif message_type == "registry_progress" and hasattr(manage_window, "handle_registry_progress"):
                    manage_window.handle_registry_progress(payload)

            if message_type == "registry_result" and request_id:
                routes.pop(request_id, None)
            return
        original_handle(self, payload)

    app_class._handle_websocket_message = handle_websocket_message