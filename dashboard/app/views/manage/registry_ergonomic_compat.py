"""Compatibility and ergonomic refinements for the Registry UI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from app.views.manage.registry_ergonomic_tab import ErgonomicRegistryTab as _BaseErgonomicRegistryTab


_OriginalPanedWindow = tk.PanedWindow
_OriginalScrollbar = ttk.Scrollbar


class _CompatiblePanedWindow(_OriginalPanedWindow):
    """Classic PanedWindow that ignores options unsupported by some Tcl/Tk builds."""

    def __init__(self, master=None, cnf=None, **kwargs):
        safe_cnf = dict(cnf or {})
        safe_cnf.pop("highlightthickness", None)
        kwargs.pop("highlightthickness", None)
        super().__init__(master, safe_cnf, **kwargs)


class _ProviderStyleScrollbar(ctk.CTkScrollbar):
    """CTk scrollbar matching the one used by the Provider tab."""

    def __init__(self, master=None, orient="vertical", **kwargs):
        orientation = kwargs.pop("orientation", orient)
        super().__init__(master, orientation=orientation, **kwargs)


class ErgonomicRegistryTab(_BaseErgonomicRegistryTab):
    """Ergonomic Registry tab with Python 3.13/Tk and layout compatibility."""

    def _build_explorer(self, frame) -> None:
        # The tab frame is initially configured with row 0 weighted by the base
        # sections builder. Explorer uses row 0 only for the compact toolbar, so
        # keeping that weight wastes roughly half of the available vertical space.
        frame.grid_rowconfigure(0, weight=0)
        frame.grid_rowconfigure(1, weight=1)

        # The ergonomic explorer uses tk.PanedWindow and ttk.Scrollbar directly.
        # Some Tcl/Tk builds reject `highlightthickness` on PanedWindow, while the
        # rest of MoonHard (Provider included) uses CTkScrollbar. Swap both only
        # while Explorer is constructed, then restore the original classes.
        original_paned = tk.PanedWindow
        original_scrollbar = ttk.Scrollbar
        tk.PanedWindow = _CompatiblePanedWindow
        ttk.Scrollbar = _ProviderStyleScrollbar
        try:
            super()._build_explorer(frame)
        finally:
            tk.PanedWindow = original_paned
            ttk.Scrollbar = original_scrollbar
