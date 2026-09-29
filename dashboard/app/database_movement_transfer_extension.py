"""Enables the Movement Transfer Database tab extension."""

from app.views import client_manage_window
from app.views.manage.database_movement_transfer_tab import MovementTransferDatabaseTab


def install_database_movement_transfer_extension() -> None:
    """Uses the extended Database tab for newly opened Manage windows."""

    client_manage_window.DatabaseTab = MovementTransferDatabaseTab
