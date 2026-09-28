"""Registry Diagnostic & Management Center UI."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk

from app.ui.theme import (
    COLORS,
    FONTS,
    SPACING,
    apply_treeview_style,
    danger_button_style,
    primary_button_style,
    secondary_button_style,
)


logger = logging.getLogger(__name__)


class RegistryValueDialog(ctk.CTkToplevel):
    """Editor για Registry values με type-aware textual input."""

    TYPES = ["REG_SZ", "REG_EXPAND_SZ", "REG_DWORD", "REG_QWORD", "REG_MULTI_SZ", "REG_BINARY"]

    def __init__(self, parent, *, title: str, value_name: str = "", value_type: str = "REG_SZ", value_text: str = "", allow_name_edit: bool = True) -> None:
        super().__init__(parent)
        self.result: dict[str, str] | None = None
        self.title(title)
        self.geometry("620x460")
        self.minsize(520, 380)
        self.configure(fg_color=COLORS.background)
        self.transient(parent)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(self, text="Value name", font=FONTS.body_bold, text_color=COLORS.text_primary).grid(row=0, column=0, padx=20, pady=(18, 4), sticky="w")
        self.name_entry = ctk.CTkEntry(self, height=36)
        self.name_entry.grid(row=1, column=0, padx=20, sticky="ew")
        self.name_entry.insert(0, value_name)
        if not allow_name_edit:
            self.name_entry.configure(state="disabled")

        ctk.CTkLabel(self, text="Type", font=FONTS.body_bold, text_color=COLORS.text_primary).grid(row=2, column=0, padx=20, pady=(14, 4), sticky="w")
        self.type_menu = ctk.CTkOptionMenu(self, values=self.TYPES)
        self.type_menu.grid(row=3, column=0, padx=20, sticky="ew")
        self.type_menu.set(value_type if value_type in self.TYPES else "REG_SZ")

        ctk.CTkLabel(self, text="Data", font=FONTS.body_bold, text_color=COLORS.text_primary).grid(row=4, column=0, padx=20, pady=(14, 4), sticky="w")
        self.data_text = ctk.CTkTextbox(self, font=FONTS.mono_body)
        self.data_text.grid(row=5, column=0, padx=20, pady=(0, 12), sticky="nsew")
        self.data_text.insert("1.0", value_text)

        hint = "REG_DWORD/QWORD: decimal or 0xHEX • REG_MULTI_SZ: one line per item • REG_BINARY: hex bytes"
        ctk.CTkLabel(self, text=hint, font=FONTS.small, text_color=COLORS.text_muted).grid(row=6, column=0, padx=20, pady=(0, 10), sticky="w")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=7, column=0, padx=20, pady=(0, 18), sticky="e")
        ctk.CTkButton(buttons, text="Cancel", width=100, command=self.destroy, **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Save", width=110, command=self._save, **primary_button_style()).pack(side="left", padx=6)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-Return>", lambda _event: self._save())

    def _save(self) -> None:
        name = self.name_entry.get() if str(self.name_entry.cget("state")) != "disabled" else self.name_entry.get()
        self.result = {
            "value_name": name,
            "value_type": self.type_menu.get(),
            "value": self.data_text.get("1.0", "end-1c"),
        }
        self.destroy()


class RegistryTab(ctk.CTkFrame):
    """Remote Registry Explorer + diagnostics, snapshots/restore and profiles."""

    def __init__(self, parent, *, client_code: str, on_registry_request_callback: Callable[[dict[str, Any]], bool | None]) -> None:
        super().__init__(parent, fg_color="transparent")
        self.client_code = client_code
        self.on_registry_request_callback = on_registry_request_callback
        self.pending: dict[str, dict[str, Any]] = {}
        self.current_values: dict[str, dict[str, Any]] = {}
        self.current_subkeys: list[str] = []
        self.history_rows: dict[str, dict[str, Any]] = {}
        self.profile_rows: dict[str, dict[str, Any]] = {}
        self.session_favorites: list[tuple[str, str, str]] = []
        self._last_import_text = ""

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_navigation()
        self._build_sections()
        self.after(250, self.load_context)
        self.after(500, self.refresh_current_key)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS.surface, corner_radius=SPACING.card_radius, border_width=1, border_color=COLORS.border_soft)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Registry Diagnostic & Management Center", font=FONTS.subtitle, text_color=COLORS.text_primary).grid(row=0, column=0, padx=16, pady=(12, 2), sticky="w")
        self.status_label = ctk.CTkLabel(header, text="Ready", font=FONTS.small, text_color=COLORS.text_secondary)
        self.status_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")
        ctk.CTkButton(header, text="Diagnostics", width=120, command=self.run_diagnostics, **secondary_button_style()).grid(row=0, column=1, rowspan=2, padx=16, pady=12)

    def _build_navigation(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLORS.surface, corner_radius=SPACING.small_radius)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        bar.grid_columnconfigure(2, weight=1)

        self.hive_menu = ctk.CTkOptionMenu(bar, values=["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], width=105, command=lambda _v: self._on_scope_changed())
        self.hive_menu.grid(row=0, column=0, padx=(10, 5), pady=10)
        self.hive_menu.set("HKLM")
        self.view_menu = ctk.CTkOptionMenu(bar, values=["default", "64", "32"], width=90, command=lambda _v: self._on_scope_changed())
        self.view_menu.grid(row=0, column=1, padx=5, pady=10)
        self.view_menu.set("default")

        self.path_entry = ctk.CTkEntry(bar, placeholder_text=r"SOFTWARE\...", font=FONTS.mono_body)
        self.path_entry.grid(row=0, column=2, padx=5, pady=10, sticky="ew")
        self.path_entry.bind("<Return>", lambda _event: self.refresh_current_key())

        ctk.CTkButton(bar, text="Back", width=70, command=self.go_back, **secondary_button_style()).grid(row=0, column=3, padx=4, pady=10)
        ctk.CTkButton(bar, text="Go", width=65, command=self.refresh_current_key, **primary_button_style()).grid(row=0, column=4, padx=4, pady=10)
        ctk.CTkButton(bar, text="★", width=42, command=self.add_favorite, **secondary_button_style()).grid(row=0, column=5, padx=(4, 10), pady=10)

    def _build_sections(self) -> None:
        self.sections = ctk.CTkTabview(self, fg_color=COLORS.surface, segmented_button_fg_color=COLORS.surface_light, segmented_button_selected_color=COLORS.accent, segmented_button_selected_hover_color=COLORS.accent_hover)
        self.sections.grid(row=2, column=0, sticky="nsew")
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
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(8, 8))
        toolbar.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(toolbar, placeholder_text="Search key / value / data...")
        self.search_entry.grid(row=0, column=0, padx=(4, 6), sticky="ew")
        self.search_entry.bind("<Return>", lambda _event: self.search_registry())
        ctk.CTkButton(toolbar, text="Search", width=85, command=self.search_registry, **secondary_button_style()).grid(row=0, column=1, padx=3)
        ctk.CTkButton(toolbar, text="Refresh", width=85, command=self.refresh_current_key, **secondary_button_style()).grid(row=0, column=2, padx=3)
        ctk.CTkButton(toolbar, text="New Key", width=85, command=self.create_key, **secondary_button_style()).grid(row=0, column=3, padx=3)
        ctk.CTkButton(toolbar, text="New Value", width=92, command=self.create_value, **secondary_button_style()).grid(row=0, column=4, padx=3)
        ctk.CTkButton(toolbar, text="Edit", width=70, command=self.edit_value, **secondary_button_style()).grid(row=0, column=5, padx=3)
        ctk.CTkButton(toolbar, text="Delete", width=75, command=self.delete_selected, **danger_button_style()).grid(row=0, column=6, padx=3)
        ctk.CTkButton(toolbar, text="Export", width=75, command=self.export_current, **secondary_button_style()).grid(row=0, column=7, padx=3)
        ctk.CTkButton(toolbar, text="Import", width=75, command=self.open_import_dialog, **secondary_button_style()).grid(row=0, column=8, padx=(3, 4))

        panes = ctk.CTkFrame(frame, fg_color="transparent")
        panes.grid(row=1, column=0, sticky="nsew")
        panes.grid_columnconfigure(0, weight=1)
        panes.grid_columnconfigure(1, weight=2)
        panes.grid_rowconfigure(0, weight=1)

        style = apply_treeview_style("Registry.Treeview")
        left = ctk.CTkFrame(panes, fg_color=COLORS.surface_light, corner_radius=SPACING.small_radius)
        left.grid(row=0, column=0, padx=(4, 5), pady=(0, 4), sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="Subkeys", font=FONTS.body_bold).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.subkeys_tree = ttk.Treeview(left, columns=("name",), show="headings", style=style)
        self.subkeys_tree.heading("name", text="Name")
        self.subkeys_tree.column("name", width=280, anchor="w")
        self.subkeys_tree.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.subkeys_tree.bind("<Double-1>", self._open_selected_subkey)

        right = ctk.CTkFrame(panes, fg_color=COLORS.surface_light, corner_radius=SPACING.small_radius)
        right.grid(row=0, column=1, padx=(5, 4), pady=(0, 4), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(right, text="Values", font=FONTS.body_bold).grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.values_tree = ttk.Treeview(right, columns=("name", "type", "data"), show="headings", style=style)
        self.values_tree.heading("name", text="Name")
        self.values_tree.heading("type", text="Type")
        self.values_tree.heading("data", text="Data")
        self.values_tree.column("name", width=180, anchor="w")
        self.values_tree.column("type", width=120, anchor="w")
        self.values_tree.column("data", width=520, anchor="w")
        self.values_tree.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.values_tree.bind("<Double-1>", lambda _event: self.edit_value())

    def _build_diagnostics(self, frame) -> None:
        wrapper = ctk.CTkFrame(frame, fg_color="transparent")
        wrapper.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)
        ctk.CTkButton(wrapper, text="Run Registry Diagnostics", command=self.run_diagnostics, **primary_button_style()).grid(row=0, column=0, pady=(4, 8), sticky="w")
        style = apply_treeview_style("Registry.Diagnostics.Treeview")
        self.diagnostics_tree = ttk.Treeview(wrapper, columns=("check", "status", "details"), show="headings", style=style)
        for col, text, width in (("check", "Check", 230), ("status", "Status", 100), ("details", "Details", 700)):
            self.diagnostics_tree.heading(col, text=text)
            self.diagnostics_tree.column(col, width=width, anchor="w")
        self.diagnostics_tree.grid(row=1, column=0, sticky="nsew")

    def _build_snapshots(self, frame) -> None:
        wrapper = ctk.CTkFrame(frame, fg_color="transparent")
        wrapper.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(wrapper, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        ctk.CTkButton(toolbar, text="Create Snapshot", command=self.create_snapshot, **primary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Refresh History", command=self.refresh_history, **secondary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Compare", command=self.compare_selected_snapshot, **secondary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Restore", command=self.restore_selected_snapshot, **danger_button_style()).pack(side="left", padx=3)
        style = apply_treeview_style("Registry.History.Treeview")
        self.history_tree = ttk.Treeview(wrapper, columns=("created", "reason", "hive", "path", "view", "entries"), show="headings", style=style)
        headings = (("created", "Created", 180), ("reason", "Reason", 150), ("hive", "Hive", 80), ("path", "Path", 390), ("view", "View", 65), ("entries", "Entries", 80))
        for col, text, width in headings:
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.grid(row=1, column=0, sticky="nsew")

    def _build_profiles(self, frame) -> None:
        wrapper = ctk.CTkFrame(frame, fg_color="transparent")
        wrapper.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(wrapper, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(4, 8))
        ctk.CTkButton(toolbar, text="Refresh", command=self.refresh_profiles, **secondary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="New from selected value", command=self.create_profile_from_selected, **secondary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Check", command=self.check_selected_profile, **primary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Dry Run", command=lambda: self.apply_selected_profile(True), **secondary_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Apply", command=lambda: self.apply_selected_profile(False), **danger_button_style()).pack(side="left", padx=3)
        ctk.CTkButton(toolbar, text="Delete", command=self.delete_selected_profile, **danger_button_style()).pack(side="left", padx=3)
        style = apply_treeview_style("Registry.Profiles.Treeview")
        self.profiles_tree = ttk.Treeview(wrapper, columns=("name", "description", "entries"), show="headings", style=style)
        self.profiles_tree.heading("name", text="Profile")
        self.profiles_tree.heading("description", text="Description")
        self.profiles_tree.heading("entries", text="Entries")
        self.profiles_tree.column("name", width=260, anchor="w")
        self.profiles_tree.column("description", width=650, anchor="w")
        self.profiles_tree.column("entries", width=80, anchor="center")
        self.profiles_tree.grid(row=1, column=0, sticky="nsew")

    def _request(self, operation: str, parameters: dict[str, Any] | None = None, *, meta: dict[str, Any] | None = None) -> str:
        request_id = str(uuid.uuid4())
        payload = {"type": "registry_request", "request_id": request_id, "client_code": self.client_code, "operation": operation, "parameters": parameters or {}}
        self.pending[request_id] = {"operation": operation, **(meta or {})}
        self._set_status(f"{operation}...")
        try:
            sent = self.on_registry_request_callback(payload)
        except Exception as exc:
            self.pending.pop(request_id, None)
            self._set_status(str(exc), error=True)
            return ""
        if sent is False:
            self.pending.pop(request_id, None)
            self._set_status("Registry request was not sent. Check Dashboard connection.", error=True)
            return ""
        return request_id

    def load_context(self) -> None:
        self._request("context")

    def refresh_current_key(self) -> None:
        self._request("list_key", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get()})

    def _on_scope_changed(self) -> None:
        self.refresh_current_key()

    def go_back(self) -> None:
        path = self.path_entry.get().strip().strip("\\")
        parent = path.rsplit("\\", 1)[0] if "\\" in path else ""
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, parent)
        self.refresh_current_key()

    def _open_selected_subkey(self, _event=None) -> None:
        selected = self.subkeys_tree.selection()
        if not selected:
            return
        name = self.subkeys_tree.item(selected[0], "values")[0]
        current = self.path_entry.get().strip().strip("\\")
        new_path = f"{current}\\{name}" if current else str(name)
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, new_path)
        self.refresh_current_key()

    def add_favorite(self) -> None:
        item = (self.hive_menu.get(), self.path_entry.get().strip(), self.view_menu.get())
        if item not in self.session_favorites:
            self.session_favorites.append(item)
        self._set_status(f"Favorite added for this session: {item[0]}\\{item[1]}")

    def search_registry(self) -> None:
        query = self.search_entry.get().strip()
        if not query:
            return
        self._request("search", {"query": query, "hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), "search_keys": True, "search_names": True, "search_data": True, "max_results": 300, "max_depth": 14})

    def create_key(self) -> None:
        dialog = ctk.CTkInputDialog(text="New key name (under current path):", title="Create Registry Key")
        name = dialog.get_input()
        if not name:
            return
        current = self.path_entry.get().strip().strip("\\")
        path = f"{current}\\{name.strip()}" if current else name.strip()
        self._request("create_key", {"hive": self.hive_menu.get(), "path": path, "view": self.view_menu.get()})

    def create_value(self) -> None:
        dialog = RegistryValueDialog(self, title="Create Registry Value")
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._request("set_value", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), **dialog.result})

    def _selected_value_payload(self) -> dict[str, Any] | None:
        selected = self.values_tree.selection()
        if not selected:
            return None
        return self.current_values.get(selected[0])

    @staticmethod
    def _editable_data(value: dict[str, Any]) -> str:
        value_type = value.get("type")
        data = value.get("data")
        if value_type == "REG_MULTI_SZ" and isinstance(data, list):
            return "\n".join(str(item) for item in data)
        if value_type == "REG_BINARY":
            return str(value.get("display_data") or "")
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False)
        return str(data if data is not None else "")

    def edit_value(self) -> None:
        value = self._selected_value_payload()
        if not value:
            self._set_status("Select a Registry value first.", error=True)
            return
        dialog = RegistryValueDialog(self, title="Edit Registry Value", value_name=str(value.get("name") or ""), value_type=str(value.get("type") or "REG_SZ"), value_text=self._editable_data(value), allow_name_edit=False)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._request("set_value", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), **dialog.result})

    def delete_selected(self) -> None:
        value = self._selected_value_payload()
        if value:
            answer = ctk.CTkInputDialog(text=f"Type DELETE to remove value '{value.get('name') or '(Default)'}'.\nAn automatic backup will be created first.", title="Confirm Registry Delete").get_input()
            if answer != "DELETE":
                return
            self._request("delete_value", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), "value_name": str(value.get("name") or "")})
            return
        selected = self.subkeys_tree.selection()
        if not selected:
            self._set_status("Select a subkey or value first.", error=True)
            return
        name = str(self.subkeys_tree.item(selected[0], "values")[0])
        current = self.path_entry.get().strip().strip("\\")
        path = f"{current}\\{name}" if current else name
        answer = ctk.CTkInputDialog(text=f"Type DELETE TREE to recursively remove:\n{self.hive_menu.get()}\\{path}\n\nA backup will be created first.", title="Confirm Registry Tree Delete").get_input()
        if answer != "DELETE TREE":
            return
        self._request("delete_key", {"hive": self.hive_menu.get(), "path": path, "view": self.view_menu.get(), "recursive": True})

    def run_diagnostics(self) -> None:
        self.sections.set("Diagnostics")
        self._request("diagnostics")

    def create_snapshot(self) -> None:
        self.sections.set("Snapshots & Restore")
        self._request("snapshot", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), "max_entries": 10000})

    def refresh_history(self) -> None:
        self._request("history", {"limit": 300})

    def _selected_history(self) -> dict[str, Any] | None:
        selected = self.history_tree.selection()
        return self.history_rows.get(selected[0]) if selected else None

    def compare_selected_snapshot(self) -> None:
        item = self._selected_history()
        if not item:
            self._set_status("Select a snapshot/backup first.", error=True)
            return
        self._request("compare_snapshot", {"backup_id": item["backup_id"]})

    def restore_selected_snapshot(self) -> None:
        item = self._selected_history()
        if not item:
            self._set_status("Select a snapshot/backup first.", error=True)
            return
        answer = ctk.CTkInputDialog(text=f"Type RESTORE to restore backup:\n{item['backup_id']}\n\nA new pre-restore backup will be created first.", title="Confirm Registry Restore").get_input()
        if answer != "RESTORE":
            return
        self._request("restore_backup", {"backup_id": item["backup_id"]})

    def refresh_profiles(self) -> None:
        self._request("profile_list")

    def _selected_profile(self) -> dict[str, Any] | None:
        selected = self.profiles_tree.selection()
        return self.profile_rows.get(selected[0]) if selected else None

    def create_profile_from_selected(self) -> None:
        value = self._selected_value_payload()
        if not value:
            self.sections.set("Explorer")
            self._set_status("Select a Registry value in Explorer first.", error=True)
            return
        name = ctk.CTkInputDialog(text="Profile name:", title="Create Registry Profile").get_input()
        if not name:
            return
        entry = {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), "value_name": str(value.get("name") or ""), "value_type": str(value.get("type") or "REG_SZ"), "value": value.get("data")}
        self._request("profile_save", {"name": name.strip(), "description": f"Created from {self.hive_menu.get()}\\{self.path_entry.get().strip()}", "entries": [entry]})

    def check_selected_profile(self) -> None:
        item = self._selected_profile()
        if item:
            self._request("profile_check", {"profile_id": item["profile_id"]})

    def apply_selected_profile(self, dry_run: bool) -> None:
        item = self._selected_profile()
        if not item:
            self._set_status("Select a profile first.", error=True)
            return
        if not dry_run:
            answer = ctk.CTkInputDialog(text=f"Type APPLY to apply profile '{item.get('name')}'.\nEvery change will have an automatic backup.", title="Confirm Registry Profile Apply").get_input()
            if answer != "APPLY":
                return
        self._request("profile_apply", {"profile_id": item["profile_id"], "mode": "all", "dry_run": dry_run})

    def delete_selected_profile(self) -> None:
        item = self._selected_profile()
        if not item:
            return
        if not messagebox.askyesno("Delete Registry Profile", f"Delete profile '{item.get('name')}'?"):
            return
        self._request("profile_delete", {"profile_id": item["profile_id"]})

    def export_current(self) -> None:
        self._request("export_reg", {"hive": self.hive_menu.get(), "path": self.path_entry.get().strip(), "view": self.view_menu.get(), "max_entries": 10000})

    def open_import_dialog(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Safe .reg Import")
        window.geometry("820x600")
        window.configure(fg_color=COLORS.background)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(window, text="Paste .reg content. Preview is required before Apply.", font=FONTS.body_bold).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        textbox = ctk.CTkTextbox(window, font=FONTS.mono_body)
        textbox.grid(row=1, column=0, padx=16, pady=6, sticky="nsew")
        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.grid(row=2, column=0, padx=16, pady=(6, 14), sticky="e")

        def preview() -> None:
            text = textbox.get("1.0", "end-1c")
            self._last_import_text = text
            self._request("import_reg_preview", {"reg_text": text, "view": self.view_menu.get()})

        def apply() -> None:
            text = textbox.get("1.0", "end-1c")
            if not text or text != self._last_import_text:
                messagebox.showwarning("Preview required", "Run Preview after the last edit before applying.")
                return
            answer = ctk.CTkInputDialog(text="Type IMPORT to apply the previewed .reg changes.\nAutomatic backups will be created before writes.", title="Confirm Registry Import").get_input()
            if answer == "IMPORT":
                self._request("import_reg_apply", {"reg_text": text, "view": self.view_menu.get()})

        ctk.CTkButton(buttons, text="Preview", command=preview, **secondary_button_style()).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Apply", command=apply, **danger_button_style()).pack(side="left", padx=4)

    def handle_progress(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") != self.client_code:
            return
        message = str(payload.get("message") or "Working...")
        current = payload.get("current")
        total = payload.get("total")
        suffix = f" ({current}/{total})" if current is not None and total else ""
        self._set_status(message + suffix)

    def handle_result(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") != self.client_code:
            return
        request_id = str(payload.get("request_id") or "")
        operation = str(payload.get("operation") or "")
        self.pending.pop(request_id, None)

        if not payload.get("success"):
            self._set_status(str(payload.get("error") or "Registry operation failed."), error=True)
            return

        handlers = {
            "context": self._handle_context,
            "list_key": self._handle_list_key,
            "search": self._handle_search,
            "diagnostics": self._handle_diagnostics,
            "snapshot": self._handle_snapshot,
            "history": self._handle_history,
            "compare_snapshot": self._handle_compare,
            "restore_backup": self._handle_mutation,
            "create_key": self._handle_mutation,
            "set_value": self._handle_mutation,
            "delete_value": self._handle_mutation,
            "delete_key": self._handle_mutation,
            "profile_list": self._handle_profile_list,
            "profile_save": self._handle_profile_mutation,
            "profile_delete": self._handle_profile_mutation,
            "profile_check": self._handle_profile_check,
            "profile_apply": self._handle_profile_apply,
            "export_reg": self._handle_export,
            "import_reg_preview": self._handle_import_preview,
            "import_reg_apply": self._handle_mutation,
        }
        handler = handlers.get(operation)
        if handler:
            handler(payload)
        else:
            self._set_status(f"{operation} completed.")

    def _handle_context(self, payload: dict[str, Any]) -> None:
        warning = str(payload.get("hkcu_warning") or "")
        admin = "Admin" if payload.get("is_admin") else "Standard rights"
        arch = payload.get("os_architecture") or "?"
        self._set_status(f"Registry ready • {admin} • OS {arch}" + (f" • {warning}" if warning else ""), error=bool(warning))

    def _handle_list_key(self, payload: dict[str, Any]) -> None:
        for tree in (self.subkeys_tree, self.values_tree):
            for item in tree.get_children():
                tree.delete(item)
        self.current_values.clear()
        self.current_subkeys = []
        for subkey in payload.get("subkeys") or []:
            name = str(subkey.get("name") or "")
            self.current_subkeys.append(name)
            self.subkeys_tree.insert("", "end", values=(name,))
        for value in payload.get("values") or []:
            item_id = self.values_tree.insert("", "end", values=(value.get("name") or "(Default)", value.get("type"), value.get("display_data")))
            self.current_values[item_id] = value
        self._set_status(f"Loaded {payload.get('subkey_count', 0)} subkeys and {payload.get('value_count', 0)} values.")

    def _handle_search(self, payload: dict[str, Any]) -> None:
        window = ctk.CTkToplevel(self)
        window.title(f"Registry Search - {payload.get('query', '')}")
        window.geometry("1050x620")
        window.configure(fg_color=COLORS.background)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(window, text=f"{payload.get('count', 0)} matches • {payload.get('visited_keys', 0)} keys checked" + (" • truncated" if payload.get("truncated") else ""), font=FONTS.body_bold).grid(row=0, column=0, padx=12, pady=10, sticky="w")
        tree = ttk.Treeview(window, columns=("kind", "hive", "path", "name", "type", "data"), show="headings", style=apply_treeview_style("Registry.Search.Treeview"))
        for col, title, width in (("kind", "Kind", 70), ("hive", "Hive", 70), ("path", "Path", 360), ("name", "Name", 170), ("type", "Type", 110), ("data", "Data", 360)):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        tree.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        for item in payload.get("results") or []:
            tree.insert("", "end", values=(item.get("kind"), item.get("hive"), item.get("path"), item.get("name"), item.get("type", ""), item.get("display_data", "")))
        self._set_status(f"Search completed: {payload.get('count', 0)} matches.")

    def _handle_diagnostics(self, payload: dict[str, Any]) -> None:
        for item in self.diagnostics_tree.get_children():
            self.diagnostics_tree.delete(item)
        for check in payload.get("checks") or []:
            self.diagnostics_tree.insert("", "end", values=(check.get("name"), check.get("status"), check.get("details")))
        self._set_status(f"Diagnostics completed: {payload.get('count', 0)} checks.")

    def _handle_snapshot(self, payload: dict[str, Any]) -> None:
        self._set_status(f"Snapshot created: {payload.get('backup_id') or payload.get('snapshot_id')} ({payload.get('entry_count', 0)} entries).")
        self.refresh_history()

    def _handle_history(self, payload: dict[str, Any]) -> None:
        self.history_rows.clear()
        for row in self.history_tree.get_children():
            self.history_tree.delete(row)
        for item in payload.get("items") or []:
            item_id = self.history_tree.insert("", "end", values=(item.get("created_at"), item.get("reason"), item.get("hive"), item.get("path"), item.get("view"), item.get("entry_count")))
            self.history_rows[item_id] = item
        self._set_status(f"Loaded {payload.get('count', 0)} Registry backups/snapshots.")

    def _handle_compare(self, payload: dict[str, Any]) -> None:
        summary = f"Same: {payload.get('same_count', 0)}\nAdded: {len(payload.get('added') or [])}\nRemoved: {len(payload.get('removed') or [])}\nChanged: {len(payload.get('changed') or [])}"
        details = {"added": payload.get("added") or [], "removed": payload.get("removed") or [], "changed": payload.get("changed") or []}
        self._show_json("Registry Snapshot Compare", summary, details)
        self._set_status(f"Snapshot compare completed: {payload.get('different_count', 0)} differences.")

    def _handle_mutation(self, payload: dict[str, Any]) -> None:
        backup = payload.get("backup_id") or payload.get("pre_restore_backup_id")
        self._set_status(f"{payload.get('operation')} completed." + (f" Backup: {backup}" if backup else ""))
        self.refresh_current_key()
        self.refresh_history()

    def _handle_profile_list(self, payload: dict[str, Any]) -> None:
        self.profile_rows.clear()
        for row in self.profiles_tree.get_children():
            self.profiles_tree.delete(row)
        for profile in payload.get("profiles") or []:
            item_id = self.profiles_tree.insert("", "end", values=(profile.get("name"), profile.get("description"), profile.get("entry_count")))
            self.profile_rows[item_id] = profile
        self._set_status(f"Loaded {payload.get('count', 0)} Registry profiles.")

    def _handle_profile_mutation(self, payload: dict[str, Any]) -> None:
        self._set_status(f"{payload.get('operation')} completed.")
        self.refresh_profiles()

    def _handle_profile_check(self, payload: dict[str, Any]) -> None:
        self._show_json("Registry Profile Check", f"OK: {payload.get('ok_count', 0)} • Problems: {payload.get('problem_count', 0)}", payload.get("results") or [])
        self._set_status(f"Profile check completed: {payload.get('problem_count', 0)} differences.")

    def _handle_profile_apply(self, payload: dict[str, Any]) -> None:
        self._show_json("Registry Profile Apply", f"Planned: {payload.get('planned_count', 0)} • Applied: {payload.get('applied_count', 0)} • Dry run: {payload.get('dry_run')}", payload.get("planned") or [])
        self._set_status("Profile dry run completed." if payload.get("dry_run") else f"Profile applied: {payload.get('applied_count', 0)} changes.")
        if not payload.get("dry_run"):
            self.refresh_current_key()
            self.refresh_history()

    def _handle_export(self, payload: dict[str, Any]) -> None:
        path = filedialog.asksaveasfilename(title="Save Registry Export", defaultextension=".reg", filetypes=[("Registry files", "*.reg"), ("All files", "*.*")])
        if not path:
            self._set_status("Registry export generated; save cancelled.")
            return
        Path(path).write_text(str(payload.get("reg_text") or ""), encoding="utf-16")
        self._set_status(f"Registry export saved: {path}")

    def _handle_import_preview(self, payload: dict[str, Any]) -> None:
        self._show_json("Safe .reg Import Preview", f"Operations: {payload.get('count', 0)}", payload.get("operations") or [])
        self._set_status(f"Import preview completed: {payload.get('count', 0)} operations.")

    def _show_json(self, title: str, summary: str, data: Any) -> None:
        window = ctk.CTkToplevel(self)
        window.title(title)
        window.geometry("900x650")
        window.configure(fg_color=COLORS.background)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(window, text=summary, font=FONTS.body_bold, justify="left").grid(row=0, column=0, padx=14, pady=12, sticky="w")
        textbox = ctk.CTkTextbox(window, font=FONTS.mono_body)
        textbox.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        textbox.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        textbox.configure(state="disabled")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(text=str(text)[:1200], text_color=COLORS.danger if error else COLORS.text_secondary)
        logger.warning("Registry UI: %s", text) if error else logger.info("Registry UI: %s", text)
