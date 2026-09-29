"""Install the ergonomic Provider tab without modifying the large Manage module."""

from __future__ import annotations

from app.views.manage.provider_ergonomic_tab import ErgonomicProviderTab


def install_provider_dashboard_extension() -> None:
    """Swap the ProviderTab constructor used by ClientManageWindow."""

    import app.views.client_manage_window as manage_window_module

    if getattr(manage_window_module, "_provider_ergonomic_extension_installed", False):
        return

    manage_window_module._provider_ergonomic_extension_installed = True
    manage_window_module.ProviderTab = ErgonomicProviderTab
