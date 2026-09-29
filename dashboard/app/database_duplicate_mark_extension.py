"""Ενεργοποιεί το extended Database tab χωρίς αλλαγές στο legacy Manage window."""

from app.views import client_manage_window
from app.views.manage.database_duplicate_mark_tab import DuplicateMarkDatabaseTab


def install_database_duplicate_mark_extension() -> None:
    """Αντικαθιστά μόνο το DatabaseTab class που χρησιμοποιούν νέα Manage windows."""

    client_manage_window.DatabaseTab = DuplicateMarkDatabaseTab
