"""Registry Dashboard extension χωρίς αλλαγές στα μεγάλα dashboard modules."""

from __future__ import annotations

import logging
from typing import Any

from app.views.client_manage_window import ClientManageWindow as BaseClientManageWindow
from app.views.manage.registry_regedit_tab import RegeditRegistryTab


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
        self.registry_tab_view = RegeditRegistryTab(
            self.registry_tab,
            client_code=self.client_code,
            on_registry_request_callback=self._send_registry_request,
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

    def _send_registry_request(self, payload: dict[str, Any]) -> bool:
        websocket_client = getattr(self._registry_parent_app, "websocket_client", None)
        if not websocket_client or not websocket_client.is_connected():
            return False
        return bool(websocket_client.send_message(payload))

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
            client_code = str(payload.get("client_code") or "")
            manage_window = self.manage_windows.get(client_code)
            if manage_window and manage_window.winfo_exists():
                if message_type == "registry_result" and hasattr(manage_window, "handle_registry_result"):
                    manage_window.handle_registry_result(payload)
                elif message_type == "registry_progress" and hasattr(manage_window, "handle_registry_progress"):
                    manage_window.handle_registry_progress(payload)
            return
        original_handle(self, payload)

    app_class._handle_websocket_message = handle_websocket_message
