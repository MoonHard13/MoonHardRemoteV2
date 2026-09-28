"""Ergonomic Regedit-style Registry UI for MoonHard Dashboard."""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk
from tkinter import ttk

from app.ui.theme import (
    COLORS,
    FONTS,
    apply_treeview_style,
    card_style,
    danger_button_style,
    primary_button_style,
    secondary_button_style,
)
from app.views.manage.registry_regedit_tab import RegeditRegistryTab


class ErgonomicRegistryTab(RegeditRegistryTab):
    """Regedit-style explorer optimized for everyday remote support work."""

    def _build_header(self) -> None:
        """Compact header: keeps context visible without consuming vertical space."""

        header = ctk.CTkFrame(self, **card_style())
        header.grid(row=0, column=0, padx=16, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, padx=18, pady=(12, 7), sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row,
            text="Registry",
            font=FONTS.title,
            text_color=COLORS.text_primary,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.registry_badge = ctk.CTkLabel(
            title_row,
            text="Remote Registry",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=26,
        )
        self.registry_badge.grid(row=0, column=1, padx=(10, 0), sticky="e")

        address_row = ctk.CTkFrame(header, fg_color="transparent")
        address_row.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="ew")
        address_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            address_row,
            text="Back",
            width=66,
            height=32,
            command=self.go_back,
            **secondary_button_style(),
        ).grid(row=0, column=0, padx=(0, 7))

        self.path_entry = ctk.CTkEntry(
            address_row,
            height=32,
            font=FONTS.mono_body,
            placeholder_text=r"Computer\HKEY_LOCAL_MACHINE\SOFTWARE",
        )
        self.path_entry.grid(row=0, column=1, padx=(0, 7), sticky="ew")
        self.path_entry.bind("<Return>", lambda _event: self.navigate_address())

        ctk.CTkButton(
            address_row,
            text="Go",
            width=54,
            height=32,
            command=self.navigate_address,
            **primary_button_style(),
        ).grid(row=0, column=2, padx=(0, 7))

        self.view_menu = ctk.CTkOptionMenu(
            address_row,
            values=["default", "64", "32"],
            width=94,
            height=32,
            command=lambda _value: self._on_view_changed(),
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.view_menu.grid(row=0, column=3, padx=(0, 7))
        self.view_menu.set("default")

        ctk.CTkButton(
            address_row,
            text="Refresh",
            width=86,
            height=32,
            command=self.refresh_current_key,
            **secondary_button_style(),
        ).grid(row=0, column=4)

        search_row = ctk.CTkFrame(header, fg_color="transparent")
        search_row.grid(row=2, column=0, padx=18, pady=(0, 11), sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_row,
            height=32,
            placeholder_text="Search in selected key: key name, value name or data...",
        )
        self.search_entry.grid(row=0, column=0, padx=(0, 7), sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.search_registry())

        ctk.CTkButton(
            search_row,
            text="Search  ·  Ctrl+F",
            width=136,
            height=32,
            command=self.search_registry,
            **secondary_button_style(),
        ).grid(row=0, column=1, padx=(0, 7))

        self.status_label = ctk.CTkLabel(
            search_row,
            text="Ready",
            width=170,
            height=28,
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            anchor="center",
        )
        self.status_label.grid(row=0, column=2)

    def _build_sections(self) -> None:
        """Keep feature sections, with Explorer receiving most of the available space."""

        self.sections = ctk.CTkTabview(
            self,
            fg_color="transparent",
            segmented_button_fg_color=COLORS.surface_light,
            segmented_button_selected_color=COLORS.accent,
            segmented_button_selected_hover_color=COLORS.accent_hover,
            segmented_button_unselected_color=COLORS.surface,
            segmented_button_unselected_hover_color=COLORS.surface_hover,
        )
        self.sections.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="nsew")

        for name in ("Explorer", "Diagnostics", "Snapshots & Restore", "Profiles"):
            frame = self.sections.add(name)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

        self._build_explorer(self.sections.tab("Explorer"))
        super()._build_diagnostics(self.sections.tab("Diagnostics"))
        super()._build_snapshots(self.sections.tab("Snapshots & Restore"))
        super()._build_profiles(self.sections.tab("Profiles"))

    def _build_explorer(self, frame) -> None:
        """Build a resizable Regedit workspace with a compact context-aware toolbar."""

        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(frame, **card_style())
        toolbar.grid(row=0, column=0, pady=(6, 8), sticky="ew")
        toolbar.grid_columnconfigure(6, weight=1)

        ctk.CTkButton(
            toolbar,
            text="New Key",
            width=92,
            height=32,
            command=self.create_key,
            **secondary_button_style(),
        ).grid(row=0, column=0, padx=(12, 5), pady=9)

        ctk.CTkButton(
            toolbar,
            text="New Value",
            width=96,
            height=32,
            command=self.create_value,
            **secondary_button_style(),
        ).grid(row=0, column=1, padx=5, pady=9)

        self.modify_button = ctk.CTkButton(
            toolbar,
            text="Modify",
            width=86,
            height=32,
            command=self.edit_value,
            **primary_button_style(),
        )
        self.modify_button.grid(row=0, column=2, padx=5, pady=9)

        ctk.CTkButton(
            toolbar,
            text="Delete",
            width=82,
            height=32,
            command=self.delete_selected,
            **danger_button_style(),
        ).grid(row=0, column=3, padx=5, pady=9)

        ctk.CTkButton(
            toolbar,
            text="Snapshot",
            width=92,
            height=32,
            command=self.create_snapshot,
            **secondary_button_style(),
        ).grid(row=0, column=4, padx=5, pady=9)

        ctk.CTkButton(
            toolbar,
            text="More",
            width=76,
            height=32,
            command=self._show_more_menu,
            **secondary_button_style(),
        ).grid(row=0, column=5, padx=(5, 10), pady=9)

        self.selection_label = ctk.CTkLabel(
            toolbar,
            text="No value selected",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="e",
        )
        self.selection_label.grid(row=0, column=6, padx=(8, 12), pady=9, sticky="ew")

        workspace = ctk.CTkFrame(frame, **card_style())
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(1, weight=1)

        top_strip = ctk.CTkFrame(workspace, fg_color="transparent")
        top_strip.grid(row=0, column=0, padx=14, pady=(11, 7), sticky="ew")
        top_strip.grid_columnconfigure(1, weight=1)

        self.key_title_label = ctk.CTkLabel(
            top_strip,
            text="HKEY_LOCAL_MACHINE",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
            anchor="w",
        )
        self.key_title_label.grid(row=0, column=0, sticky="w")

        self.key_summary_label = ctk.CTkLabel(
            top_strip,
            text="",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="e",
        )
        self.key_summary_label.grid(row=0, column=1, sticky="e")

        # Native PanedWindow gives the user a draggable divider like Regedit.
        self.registry_panes = tk.PanedWindow(
            workspace,
            orient=tk.HORIZONTAL,
            sashwidth=6,
            sashrelief=tk.FLAT,
            bg=COLORS.border_soft,
            bd=0,
            highlightthickness=0,
        )
        self.registry_panes.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="nsew")

        style = apply_treeview_style("Registry.Ergonomic.Treeview")

        left_wrap = tk.Frame(self.registry_panes, bg=COLORS.background, bd=0)
        right_wrap = tk.Frame(self.registry_panes, bg=COLORS.background, bd=0)
        self.registry_panes.add(left_wrap, minsize=260, width=330, stretch="always")
        self.registry_panes.add(right_wrap, minsize=420, stretch="always")

        left_wrap.grid_columnconfigure(0, weight=1)
        left_wrap.grid_rowconfigure(0, weight=1)
        self.registry_tree = ttk.Treeview(
            left_wrap,
            show="tree",
            style=style,
            selectmode="browse",
        )
        self.registry_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(left_wrap, orient="vertical", command=self.registry_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.registry_tree.configure(yscrollcommand=tree_scroll.set)
        self.registry_tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.registry_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.registry_tree.bind("<Button-3>", self._show_key_context_menu)

        right_wrap.grid_columnconfigure(0, weight=1)
        right_wrap.grid_rowconfigure(0, weight=1)
        self.values_tree = ttk.Treeview(
            right_wrap,
            columns=("name", "type", "data"),
            show="headings",
            style=style,
            selectmode="browse",
        )
        self.values_tree.heading("name", text="Name")
        self.values_tree.heading("type", text="Type")
        self.values_tree.heading("data", text="Data")
        self.values_tree.column("name", width=215, minwidth=120, anchor="w")
        self.values_tree.column("type", width=120, minwidth=90, anchor="w")
        self.values_tree.column("data", width=620, minwidth=220, anchor="w")
        self.values_tree.grid(row=0, column=0, sticky="nsew")

        value_y = ttk.Scrollbar(right_wrap, orient="vertical", command=self.values_tree.yview)
        value_y.grid(row=0, column=1, sticky="ns")
        value_x = ttk.Scrollbar(right_wrap, orient="horizontal", command=self.values_tree.xview)
        value_x.grid(row=1, column=0, sticky="ew")
        self.values_tree.configure(yscrollcommand=value_y.set, xscrollcommand=value_x.set)
        self.values_tree.bind("<Double-1>", lambda _event: self.edit_value())
        self.values_tree.bind("<Button-3>", self._show_value_context_menu)
        self.values_tree.bind("<<TreeviewSelect>>", self._on_value_select)

        footer = ctk.CTkFrame(workspace, fg_color="transparent")
        footer.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.scope_label = ctk.CTkLabel(
            footer,
            text="",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="w",
        )
        self.scope_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            footer,
            text="F5 Refresh  ·  Ctrl+F Search  ·  Delete Remove  ·  Double-click Modify",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="e",
        ).grid(row=0, column=1, padx=(12, 0), sticky="e")

        self.subkeys_tree = self.registry_tree
        self._insert_registry_roots()
        self._bind_regedit_shortcuts()
        self._update_scope_labels()

    def _show_more_menu(self) -> None:
        """Rare actions stay available without permanently occupying toolbar space."""

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Export selected key...", command=self.export_current)
        menu.add_command(label="Import .reg...", command=self.open_import_dialog)
        menu.add_separator()
        menu.add_command(label="Copy key name", command=self.copy_current_key_name)
        menu.add_command(label="Add to favorites", command=self.add_favorite)
        menu.add_separator()
        menu.add_command(label="Registry diagnostics", command=self.run_diagnostics)

        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _on_value_select(self, _event=None) -> None:
        value = self._selected_value_payload()
        if not value:
            self.selection_label.configure(text="No value selected", text_color=COLORS.text_muted)
            return
        name = str(value.get("name") or "(Default)")
        value_type = str(value.get("type") or "")
        self.selection_label.configure(
            text=f"Selected: {name}  ·  {value_type}",
            text_color=COLORS.text_secondary,
        )

    def _sync_scope_from_tree(self, item: str) -> None:
        super()._sync_scope_from_tree(item)
        self._update_scope_labels()
        if hasattr(self, "values_tree"):
            for selected in self.values_tree.selection():
                self.values_tree.selection_remove(selected)
        if hasattr(self, "selection_label"):
            self.selection_label.configure(text="No value selected", text_color=COLORS.text_muted)

    def _render_values(self, payload: dict[str, Any]) -> None:
        super()._render_values(payload)
        self._update_scope_labels(
            subkeys=int(payload.get("subkey_count") or 0),
            values=int(payload.get("value_count") or 0),
        )

    def _update_scope_labels(self, *, subkeys: int | None = None, values: int | None = None) -> None:
        scope = self._current_scope()
        if not scope:
            return
        display_hive = self.HIVE_TO_DISPLAY.get(scope["hive"], scope["hive"])
        leaf = scope["path"].rsplit("\\", 1)[-1] if scope["path"] else display_hive
        full_path = display_hive + (f"\\{scope['path']}" if scope["path"] else "")
        if hasattr(self, "key_title_label"):
            self.key_title_label.configure(text=leaf)
        if hasattr(self, "scope_label"):
            self.scope_label.configure(text=full_path)
        if hasattr(self, "key_summary_label") and subkeys is not None and values is not None:
            self.key_summary_label.configure(text=f"{subkeys} subkeys  ·  {values} values")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        # Keep the status compact; detailed data remains in dialogs/results views.
        compact = str(text or "").replace("\n", " ")
        if len(compact) > 90:
            compact = compact[:87] + "..."
        if hasattr(self, "status_label"):
            self.status_label.configure(
                text=compact,
                text_color=COLORS.danger if error else COLORS.info,
                fg_color=COLORS.danger_soft if error else COLORS.info_soft,
            )
