"""Regedit-style Registry tab UI built on top of the existing Registry feature."""

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
from app.views.manage.registry_tab import RegistryTab, RegistryValueDialog


class RegeditRegistryTab(RegistryTab):
    """Registry tab με διάταξη και πλοήγηση παρόμοια με το Windows Regedit."""

    HIVES = (
        ("HKCR", "HKEY_CLASSES_ROOT"),
        ("HKCU", "HKEY_CURRENT_USER"),
        ("HKLM", "HKEY_LOCAL_MACHINE"),
        ("HKU", "HKEY_USERS"),
        ("HKCC", "HKEY_CURRENT_CONFIG"),
    )

    DISPLAY_TO_HIVE = {display: hive for hive, display in HIVES}
    HIVE_TO_DISPLAY = {hive: display for hive, display in HIVES}

    def __init__(self, parent, *, client_code: str, on_registry_request_callback) -> None:
        self.tree_scope: dict[str, dict[str, Any]] = {}
        self._tree_request_items: dict[str, str] = {}
        self._selected_tree_item = ""
        self.active_scope: dict[str, str] = {"hive": "HKLM", "path": ""}
        super().__init__(
            parent,
            client_code=client_code,
            on_registry_request_callback=on_registry_request_callback,
        )

    def _build_header(self) -> None:
        """Χτίζει header στην ίδια λογική με το Database tab."""

        header = ctk.CTkFrame(self, **card_style())
        header.grid(row=0, column=0, padx=16, pady=(12, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Registry",
            font=FONTS.title,
            text_color=COLORS.text_primary,
            anchor="w",
        ).grid(row=0, column=0, padx=20, pady=(14, 0), sticky="ew")

        self.registry_badge = ctk.CTkLabel(
            header,
            text="Remote Registry",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=28,
        )
        self.registry_badge.grid(row=0, column=1, padx=20, pady=(14, 0), sticky="e")

        ctk.CTkLabel(
            header,
            text="Browse and manage the remote Windows Registry with a Regedit-style explorer.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=(2, 10), sticky="ew")

        toolbar = ctk.CTkFrame(header, fg_color="transparent")
        toolbar.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            toolbar,
            text="Address",
            font=FONTS.small,
            text_color=COLORS.text_muted,
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.path_entry = ctk.CTkEntry(
            toolbar,
            height=34,
            font=FONTS.mono_body,
            placeholder_text=r"Computer\HKEY_LOCAL_MACHINE\SOFTWARE",
        )
        self.path_entry.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        self.path_entry.bind("<Return>", lambda _event: self.navigate_address())

        ctk.CTkButton(
            toolbar,
            text="Back",
            width=72,
            height=34,
            command=self.go_back,
            **secondary_button_style(),
        ).grid(row=0, column=2, padx=(0, 8))

        self.view_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["default", "64", "32"],
            width=92,
            height=34,
            command=lambda _value: self._on_view_changed(),
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.view_menu.grid(row=0, column=3, padx=(0, 8))
        self.view_menu.set("default")

        ctk.CTkButton(
            toolbar,
            text="Refresh",
            width=130,
            height=34,
            command=self.refresh_current_key,
            **secondary_button_style(),
        ).grid(row=0, column=4, padx=(0, 8))

        ctk.CTkButton(
            toolbar,
            text="Diagnostics",
            width=128,
            height=34,
            command=self.run_diagnostics,
            **primary_button_style(),
        ).grid(row=0, column=5)

        self.status_label = ctk.CTkLabel(
            header,
            text="Ready",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=28,
            anchor="w",
        )
        self.status_label.grid(
            row=3,
            column=0,
            columnspan=2,
            padx=20,
            pady=(0, 16),
            sticky="ew",
        )

    def _build_navigation(self) -> None:
        """Το Regedit tree αντικαθιστά το παλιό hive/path navigation bar."""

        self.hive_menu = tk.StringVar(value="HKLM")

    def _build_sections(self) -> None:
        self.sections = ctk.CTkTabview(
            self,
            fg_color="transparent",
            segmented_button_fg_color=COLORS.surface_light,
            segmented_button_selected_color=COLORS.accent,
            segmented_button_selected_hover_color=COLORS.accent_hover,
            segmented_button_unselected_color=COLORS.surface,
            segmented_button_unselected_hover_color=COLORS.surface_hover,
        )
        self.sections.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")

        for name in ("Explorer", "Diagnostics", "Snapshots & Restore", "Profiles"):
            frame = self.sections.add(name)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

        self._build_explorer(self.sections.tab("Explorer"))
        self._build_diagnostics(self.sections.tab("Diagnostics"))
        self._build_snapshots(self.sections.tab("Snapshots & Restore"))
        self._build_profiles(self.sections.tab("Profiles"))

    def _build_explorer(self, frame) -> None:
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        actions_card = ctk.CTkFrame(frame, **card_style())
        actions_card.grid(row=0, column=0, pady=(8, 10), sticky="ew")
        actions_card.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            actions_card,
            height=34,
            placeholder_text="Search key, value name or data...",
        )
        self.search_entry.grid(row=0, column=0, columnspan=5, padx=(16, 8), pady=(14, 7), sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.search_registry())

        ctk.CTkButton(
            actions_card,
            text="Search",
            width=135,
            height=34,
            command=self.search_registry,
            **secondary_button_style(),
        ).grid(row=0, column=5, padx=(0, 16), pady=(14, 7))

        action_specs = (
            ("New Key", self.create_key, secondary_button_style()),
            ("New Value", self.create_value, secondary_button_style()),
            ("Edit", self.edit_value, secondary_button_style()),
            ("Delete", self.delete_selected, danger_button_style()),
            ("Export", self.export_current, secondary_button_style()),
            ("Import", self.open_import_dialog, secondary_button_style()),
        )
        for index, (text, command, style) in enumerate(action_specs):
            actions_card.grid_columnconfigure(index, weight=1)
            ctk.CTkButton(
                actions_card,
                text=text,
                height=34,
                command=command,
                **style,
            ).grid(
                row=1,
                column=index,
                padx=(16 if index == 0 else 4, 16 if index == len(action_specs) - 1 else 4),
                pady=(0, 14),
                sticky="ew",
            )

        explorer_card = ctk.CTkFrame(frame, **card_style())
        explorer_card.grid(row=1, column=0, sticky="nsew")
        explorer_card.grid_rowconfigure(1, weight=1)
        explorer_card.grid_columnconfigure(0, weight=2)
        explorer_card.grid_columnconfigure(1, weight=5)

        ctk.CTkLabel(
            explorer_card,
            text="Registry hierarchy",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")

        ctk.CTkLabel(
            explorer_card,
            text="Values",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=1, padx=16, pady=(14, 8), sticky="w")

        style = apply_treeview_style("Registry.Regedit.Treeview")

        left_wrap = ctk.CTkFrame(
            explorer_card,
            fg_color=COLORS.background,
            corner_radius=10,
            border_width=1,
            border_color=COLORS.border,
        )
        left_wrap.grid(row=1, column=0, padx=(16, 6), pady=(0, 16), sticky="nsew")
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

        right_wrap = ctk.CTkFrame(
            explorer_card,
            fg_color=COLORS.background,
            corner_radius=10,
            border_width=1,
            border_color=COLORS.border,
        )
        right_wrap.grid(row=1, column=1, padx=(6, 16), pady=(0, 16), sticky="nsew")
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
        self.values_tree.column("name", width=220, minwidth=120, anchor="w")
        self.values_tree.column("type", width=130, minwidth=90, anchor="w")
        self.values_tree.column("data", width=620, minwidth=220, anchor="w")
        self.values_tree.grid(row=0, column=0, sticky="nsew")
        values_scroll = ttk.Scrollbar(right_wrap, orient="vertical", command=self.values_tree.yview)
        values_scroll.grid(row=0, column=1, sticky="ns")
        self.values_tree.configure(yscrollcommand=values_scroll.set)
        self.values_tree.bind("<Double-1>", lambda _event: self.edit_value())
        self.values_tree.bind("<Button-3>", self._show_value_context_menu)

        self.subkeys_tree = self.registry_tree
        self._insert_registry_roots()
        self._bind_regedit_shortcuts()

    def _build_diagnostics(self, frame) -> None:
        card = ctk.CTkFrame(frame, **card_style())
        card.grid(row=0, column=0, pady=(8, 0), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card,
            text="Registry diagnostics",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="w")
        ctk.CTkLabel(
            card,
            text="Check Windows, SQL Server and MoonHard-related Registry configuration without modifying values.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")
        ctk.CTkButton(
            card,
            text="Run Registry Diagnostics",
            width=220,
            height=36,
            command=self.run_diagnostics,
            **primary_button_style(),
        ).grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

        style = apply_treeview_style("Registry.Diagnostics.Treeview")
        self.diagnostics_tree = ttk.Treeview(
            card,
            columns=("check", "status", "details"),
            show="headings",
            style=style,
        )
        for col, text, width in (
            ("check", "Check", 230),
            ("status", "Status", 110),
            ("details", "Details", 700),
        ):
            self.diagnostics_tree.heading(col, text=text)
            self.diagnostics_tree.column(col, width=width, anchor="w")
        self.diagnostics_tree.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")

    def _build_snapshots(self, frame) -> None:
        card = ctk.CTkFrame(frame, **card_style())
        card.grid(row=0, column=0, pady=(8, 0), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card,
            text="Snapshots & Restore",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="w")
        ctk.CTkLabel(
            card,
            text="Capture a scoped Registry snapshot, compare changes and restore a previous state safely.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

        toolbar = ctk.CTkFrame(card, fg_color="transparent")
        toolbar.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")
        ctk.CTkButton(toolbar, text="Create Snapshot", command=self.create_snapshot, **primary_button_style()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="Refresh History", command=self.refresh_history, **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Compare", command=self.compare_selected_snapshot, **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Restore", command=self.restore_selected_snapshot, **danger_button_style()).pack(side="left", padx=6)

        style = apply_treeview_style("Registry.History.Treeview")
        self.history_tree = ttk.Treeview(
            card,
            columns=("created", "reason", "hive", "path", "view", "entries"),
            show="headings",
            style=style,
        )
        for col, text, width in (
            ("created", "Created", 180),
            ("reason", "Reason", 150),
            ("hive", "Hive", 80),
            ("path", "Path", 390),
            ("view", "View", 65),
            ("entries", "Entries", 80),
        ):
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")

    def _build_profiles(self, frame) -> None:
        card = ctk.CTkFrame(frame, **card_style())
        card.grid(row=0, column=0, pady=(8, 0), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card,
            text="Registry profiles",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 3), sticky="w")
        ctk.CTkLabel(
            card,
            text="Save known-good Registry values, check differences and apply controlled repairs.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

        toolbar = ctk.CTkFrame(card, fg_color="transparent")
        toolbar.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")
        ctk.CTkButton(toolbar, text="Refresh", command=self.refresh_profiles, **secondary_button_style()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(toolbar, text="New from selected value", command=self.create_profile_from_selected, **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Check", command=self.check_selected_profile, **primary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Dry Run", command=lambda: self.apply_selected_profile(True), **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Apply", command=lambda: self.apply_selected_profile(False), **danger_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(toolbar, text="Delete", command=self.delete_selected_profile, **danger_button_style()).pack(side="left", padx=6)

        style = apply_treeview_style("Registry.Profiles.Treeview")
        self.profiles_tree = ttk.Treeview(
            card,
            columns=("name", "description", "entries"),
            show="headings",
            style=style,
        )
        self.profiles_tree.heading("name", text="Profile")
        self.profiles_tree.heading("description", text="Description")
        self.profiles_tree.heading("entries", text="Entries")
        self.profiles_tree.column("name", width=260, anchor="w")
        self.profiles_tree.column("description", width=650, anchor="w")
        self.profiles_tree.column("entries", width=80, anchor="center")
        self.profiles_tree.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="nsew")

    def _insert_registry_roots(self) -> None:
        for item in self.registry_tree.get_children():
            self.registry_tree.delete(item)
        self.tree_scope.clear()

        computer = self.registry_tree.insert("", "end", text="Computer", open=True)
        self.tree_scope[computer] = {"kind": "computer"}

        hklm_item = ""
        for hive, display_name in self.HIVES:
            item = self.registry_tree.insert(computer, "end", text=display_name, open=False)
            self.tree_scope[item] = {
                "kind": "key",
                "hive": hive,
                "path": "",
                "loaded": False,
            }
            self.registry_tree.insert(item, "end", text="Loading...", tags=("placeholder",))
            if hive == "HKLM":
                hklm_item = item

        if hklm_item:
            self.registry_tree.selection_set(hklm_item)
            self.registry_tree.focus(hklm_item)
            self._selected_tree_item = hklm_item
            self._sync_scope_from_tree(hklm_item)

    def _bind_regedit_shortcuts(self) -> None:
        top = self.winfo_toplevel()
        top.bind("<F5>", lambda _event: self.refresh_current_key(), add="+")
        top.bind("<Control-f>", lambda _event: self.search_entry.focus_set(), add="+")
        top.bind("<Delete>", lambda _event: self.delete_selected(), add="+")

    def _on_tree_open(self, _event=None) -> None:
        item = self.registry_tree.focus()
        scope = self.tree_scope.get(item) or {}
        if scope.get("kind") != "key" or scope.get("loaded"):
            return
        self._load_tree_children(item)

    def _on_tree_select(self, _event=None) -> None:
        selection = self.registry_tree.selection()
        if not selection:
            return
        item = selection[0]
        scope = self.tree_scope.get(item) or {}
        if scope.get("kind") != "key":
            return
        self._selected_tree_item = item
        self._sync_scope_from_tree(item)
        self.refresh_current_key()

    def _sync_scope_from_tree(self, item: str) -> None:
        scope = self.tree_scope.get(item) or {}
        hive = str(scope.get("hive") or "HKLM")
        path = str(scope.get("path") or "")
        self.active_scope = {"hive": hive, "path": path}
        self.hive_menu.set(hive)
        self._show_address(hive, path)

    def _show_address(self, hive: str, path: str) -> None:
        self.path_entry.delete(0, "end")
        display_hive = self.HIVE_TO_DISPLAY.get(hive, hive)
        address = f"Computer\\{display_hive}"
        if path:
            address += f"\\{path}"
        self.path_entry.insert(0, address)

    def _load_tree_children(self, item: str, *, force: bool = False) -> None:
        scope = self.tree_scope.get(item) or {}
        if scope.get("kind") != "key":
            return
        if force:
            scope["loaded"] = False
        if scope.get("loaded"):
            return
        request_id = self._request(
            "list_key",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
            },
            meta={"purpose": "tree_expand", "tree_item": item},
        )
        if request_id:
            self._tree_request_items[request_id] = item

    def _current_scope(self) -> dict[str, str] | None:
        hive = str(self.active_scope.get("hive") or "")
        path = str(self.active_scope.get("path") or "")
        if not hive:
            return None
        return {"hive": hive, "path": path}

    def refresh_current_key(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        self._request(
            "list_key",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
            },
            meta={"purpose": "values", "tree_item": self._selected_tree_item},
        )

    def _on_view_changed(self) -> None:
        for item, scope in tuple(self.tree_scope.items()):
            if scope.get("kind") != "key":
                continue
            scope["loaded"] = False
            for child in self.registry_tree.get_children(item):
                self.registry_tree.delete(child)
            self.registry_tree.insert(item, "end", text="Loading...", tags=("placeholder",))
        self.refresh_current_key()

    def navigate_address(self) -> None:
        hive, path = self._parse_address(self.path_entry.get())
        if not hive:
            self._set_status("Invalid Registry address.", error=True)
            return
        self.active_scope = {"hive": hive, "path": path}
        self.hive_menu.set(hive)
        self._show_address(hive, path)
        self._request(
            "list_key",
            {"hive": hive, "path": path, "view": self.view_menu.get()},
            meta={"purpose": "address", "hive": hive, "path": path},
        )

    def _parse_address(self, text: str) -> tuple[str, str]:
        cleaned = str(text or "").strip().replace("/", "\\").strip("\\")
        if cleaned.lower().startswith("computer\\"):
            cleaned = cleaned.split("\\", 1)[1]
        first, separator, rest = cleaned.partition("\\")
        first_upper = first.upper()
        if first_upper in self.HIVE_TO_DISPLAY:
            return first_upper, rest if separator else ""
        hive = self.DISPLAY_TO_HIVE.get(first_upper)
        if hive:
            return hive, rest if separator else ""
        return "", ""

    def go_back(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        path = scope["path"].strip("\\")
        if not path:
            return
        parent_path = path.rsplit("\\", 1)[0] if "\\" in path else ""
        parent_item = self.registry_tree.parent(self._selected_tree_item)
        parent_scope = self.tree_scope.get(parent_item) or {}
        if parent_scope.get("kind") == "key" and parent_scope.get("hive") == scope["hive"]:
            self.registry_tree.selection_set(parent_item)
            self.registry_tree.focus(parent_item)
            self._selected_tree_item = parent_item
            self._sync_scope_from_tree(parent_item)
            self.refresh_current_key()
            return

        self.active_scope = {"hive": scope["hive"], "path": parent_path}
        self._show_address(scope["hive"], parent_path)
        self.refresh_current_key()

    def _open_selected_subkey(self, _event=None) -> None:
        return

    def search_registry(self) -> None:
        query = self.search_entry.get().strip()
        scope = self._current_scope()
        if not query or not scope:
            return
        self._request(
            "search",
            {
                "query": query,
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                "search_keys": True,
                "search_names": True,
                "search_data": True,
                "max_results": 300,
                "max_depth": 14,
            },
        )

    def add_favorite(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        item = (scope["hive"], scope["path"], self.view_menu.get())
        if item not in self.session_favorites:
            self.session_favorites.append(item)
        self._set_status(f"Favorite added for this session: {item[0]}\\{item[1]}")

    def create_key(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        name = ctk.CTkInputDialog(
            text="New key name (under current key):",
            title="Create Registry Key",
        ).get_input()
        if not name:
            return
        clean_name = name.strip().strip("\\")
        if not clean_name:
            return
        path = f"{scope['path']}\\{clean_name}" if scope["path"] else clean_name
        self._request(
            "create_key",
            {"hive": scope["hive"], "path": path, "view": self.view_menu.get()},
        )

    def create_value(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        dialog = RegistryValueDialog(self, title="Create Registry Value")
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._request(
            "set_value",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                **dialog.result,
            },
        )

    def edit_value(self) -> None:
        scope = self._current_scope()
        value = self._selected_value_payload()
        if not scope or not value:
            self._set_status("Select a Registry value first.", error=True)
            return
        dialog = RegistryValueDialog(
            self,
            title="Edit Registry Value",
            value_name=str(value.get("name") or ""),
            value_type=str(value.get("type") or "REG_SZ"),
            value_text=self._editable_data(value),
            allow_name_edit=False,
        )
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._request(
            "set_value",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                **dialog.result,
            },
        )

    def delete_selected(self) -> None:
        scope = self._current_scope()
        if not scope:
            return

        value = self._selected_value_payload()
        if value:
            answer = ctk.CTkInputDialog(
                text=(
                    f"Type DELETE to remove value '{value.get('name') or '(Default)'}'.\n"
                    "An automatic backup will be created first."
                ),
                title="Confirm Registry Delete",
            ).get_input()
            if answer != "DELETE":
                return
            self._request(
                "delete_value",
                {
                    "hive": scope["hive"],
                    "path": scope["path"],
                    "view": self.view_menu.get(),
                    "value_name": str(value.get("name") or ""),
                },
            )
            return

        if not scope["path"]:
            self._set_status("Root Registry hives cannot be deleted.", error=True)
            return

        answer = ctk.CTkInputDialog(
            text=(
                f"Type DELETE TREE to recursively remove:\n"
                f"{scope['hive']}\\{scope['path']}\n\n"
                "An automatic backup will be created first."
            ),
            title="Confirm Registry Tree Delete",
        ).get_input()
        if answer != "DELETE TREE":
            return
        self._request(
            "delete_key",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                "recursive": True,
            },
        )

    def create_snapshot(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        self.sections.set("Snapshots & Restore")
        self._request(
            "snapshot",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                "max_entries": 10000,
            },
        )

    def create_profile_from_selected(self) -> None:
        scope = self._current_scope()
        value = self._selected_value_payload()
        if not scope or not value:
            self.sections.set("Explorer")
            self._set_status("Select a Registry value in Explorer first.", error=True)
            return
        name = ctk.CTkInputDialog(text="Profile name:", title="Create Registry Profile").get_input()
        if not name:
            return
        entry = {
            "hive": scope["hive"],
            "path": scope["path"],
            "view": self.view_menu.get(),
            "value_name": str(value.get("name") or ""),
            "value_type": str(value.get("type") or "REG_SZ"),
            "value": value.get("data"),
        }
        self._request(
            "profile_save",
            {
                "name": name.strip(),
                "description": f"Created from {scope['hive']}\\{scope['path']}",
                "entries": [entry],
            },
        )

    def export_current(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        self._request(
            "export_reg",
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get(),
                "max_entries": 10000,
            },
        )

    def handle_result(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") != self.client_code:
            return

        request_id = str(payload.get("request_id") or "")
        operation = str(payload.get("operation") or "")
        pending_meta = dict(self.pending.get(request_id) or {})

        if operation != "list_key":
            super().handle_result(payload)
            return

        self.pending.pop(request_id, None)
        self._tree_request_items.pop(request_id, None)

        if not payload.get("success"):
            self._set_status(str(payload.get("error") or "Registry operation failed."), error=True)
            return

        purpose = pending_meta.get("purpose")
        if purpose == "tree_expand":
            self._handle_tree_expand(payload, str(pending_meta.get("tree_item") or ""))
            return

        if purpose == "address":
            hive = str(pending_meta.get("hive") or payload.get("hive") or "HKLM")
            path = str(pending_meta.get("path") or payload.get("path") or "")
            self.active_scope = {"hive": hive, "path": path}
            self.hive_menu.set(hive)
            self._show_address(hive, path)

        self._handle_list_key(payload)

    def _handle_tree_expand(self, payload: dict[str, Any], item: str) -> None:
        if not item or item not in self.tree_scope:
            return

        scope = self.tree_scope[item]
        for child in self.registry_tree.get_children(item):
            self.registry_tree.delete(child)

        for subkey in payload.get("subkeys") or []:
            name = str(subkey.get("name") or "")
            child_path = f"{scope['path']}\\{name}" if scope["path"] else name
            child = self.registry_tree.insert(item, "end", text=name, open=False)
            self.tree_scope[child] = {
                "kind": "key",
                "hive": scope["hive"],
                "path": child_path,
                "loaded": False,
            }
            self.registry_tree.insert(child, "end", text="Loading...", tags=("placeholder",))

        scope["loaded"] = True
        if item == self._selected_tree_item:
            self._render_values(payload)
        self._set_status(
            f"Loaded {payload.get('subkey_count', 0)} subkeys and "
            f"{payload.get('value_count', 0)} values."
        )

    def _handle_list_key(self, payload: dict[str, Any]) -> None:
        self._render_values(payload)
        self._set_status(
            f"Loaded {payload.get('subkey_count', 0)} subkeys and "
            f"{payload.get('value_count', 0)} values."
        )

    def _render_values(self, payload: dict[str, Any]) -> None:
        for item in self.values_tree.get_children():
            self.values_tree.delete(item)
        self.current_values.clear()

        for value in payload.get("values") or []:
            item_id = self.values_tree.insert(
                "",
                "end",
                values=(
                    value.get("name") or "(Default)",
                    value.get("type"),
                    value.get("display_data"),
                ),
            )
            self.current_values[item_id] = value

    def _show_key_context_menu(self, event) -> None:
        item = self.registry_tree.identify_row(event.y)
        if not item:
            return
        self.registry_tree.selection_set(item)
        self.registry_tree.focus(item)
        self._selected_tree_item = item
        scope = self.tree_scope.get(item) or {}
        if scope.get("kind") != "key":
            return
        self._sync_scope_from_tree(item)

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Expand", command=lambda: self._load_tree_children(item))
        menu.add_command(label="Refresh", command=lambda: self._refresh_tree_item(item))
        menu.add_separator()
        menu.add_command(label="New Key", command=self.create_key)
        menu.add_command(label="New Value", command=self.create_value)
        menu.add_separator()
        menu.add_command(label="Export", command=self.export_current)
        if scope.get("path"):
            menu.add_command(label="Delete", command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="Copy Key Name", command=self.copy_current_key_name)
        menu.tk_popup(event.x_root, event.y_root)

    def _show_value_context_menu(self, event) -> None:
        item = self.values_tree.identify_row(event.y)
        if item:
            self.values_tree.selection_set(item)
            self.values_tree.focus(item)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Modify...", command=self.edit_value)
        menu.add_command(label="New Value...", command=self.create_value)
        menu.add_separator()
        menu.add_command(label="Delete", command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="Copy Name", command=self.copy_selected_value_name)
        menu.add_command(label="Copy Data", command=self.copy_selected_value_data)
        menu.tk_popup(event.x_root, event.y_root)

    def _refresh_tree_item(self, item: str) -> None:
        scope = self.tree_scope.get(item) or {}
        if scope.get("kind") != "key":
            return
        scope["loaded"] = False
        for child in self.registry_tree.get_children(item):
            self.registry_tree.delete(child)
        self.registry_tree.insert(item, "end", text="Loading...", tags=("placeholder",))
        self._load_tree_children(item)
        if item == self._selected_tree_item:
            self.refresh_current_key()

    def copy_current_key_name(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        display_hive = self.HIVE_TO_DISPLAY.get(scope["hive"], scope["hive"])
        text = display_hive + (f"\\{scope['path']}" if scope["path"] else "")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("Registry key path copied.")

    def copy_selected_value_name(self) -> None:
        value = self._selected_value_payload()
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(str(value.get("name") or "(Default)"))
        self._set_status("Registry value name copied.")

    def copy_selected_value_data(self) -> None:
        value = self._selected_value_payload()
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(str(value.get("display_data") or ""))
        self._set_status("Registry value data copied.")
