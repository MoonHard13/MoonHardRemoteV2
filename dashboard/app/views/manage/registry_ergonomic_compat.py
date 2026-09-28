"""Compatibility wrapper for the ergonomic Registry UI on newer Tk builds."""

from __future__ import annotations

import tkinter as tk

from app.views.manage.registry_ergonomic_tab import ErgonomicRegistryTab as _BaseErgonomicRegistryTab


_OriginalPanedWindow = tk.PanedWindow


class _CompatiblePanedWindow(_OriginalPanedWindow):
    """Classic PanedWindow that ignores options unsupported by some Tcl/Tk builds."""

    def __init__(self, master=None, cnf=None, **kwargs):
        safe_cnf = dict(cnf or {})
        safe_cnf.pop("highlightthickness", None)
        kwargs.pop("highlightthickness", None)
        super().__init__(master, safe_cnf, **kwargs)


class ErgonomicRegistryTab(_BaseErgonomicRegistryTab):
    """Ergonomic Registry tab with Python 3.13/Tk compatibility."""

    def _build_explorer(self, frame) -> None:
        # registry_ergonomic_tab uses tk.PanedWindow directly. Some newer Tcl/Tk
        # builds reject the classic-widget option `highlightthickness`, so swap
        # in a tiny compatible wrapper only while the explorer is constructed.
        original = tk.PanedWindow
        tk.PanedWindow = _CompatiblePanedWindow
        try:
            super()._build_explorer(frame)
        finally:
            tk.PanedWindow = original
