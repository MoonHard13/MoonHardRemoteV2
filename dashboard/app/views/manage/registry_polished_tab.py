"""Final Registry Explorer polish layer for day-to-day MoonHard support work."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

from app.ui.theme import (
    COLORS,
    FONTS,
    apply_treeview_style,
    danger_button_style,
    primary_button_style,
    secondary_button_style,
)
from app.views.manage.registry_ergonomic_compat import ErgonomicRegistryTab


class PolishedRegistryTab(ErgonomicRegistryTab):
    """Ergonomic Registry UI with safer navigation and session conveniences."""

    _SESSION_STATE: dict[str, dict[str, Any]] = {}

    KEY_CONTEXT_ACTIONS = (
        "Expand",
        "Refresh",
        "New Key",
        "New Value",
        "Create Snapshot",
        "Export",
        "Add to Favorites",
        "Open Favorites",
        "Delete",
        "Copy Key Name",
    )
    VALUE_CONTEXT_ACTIONS = (
        "Modify",
        "New Value",
        "Delete",
        "Copy Name",
        "Copy Data",
        "Create Profile from Value",
    )

    def __init__(self, parent, *, client_code: str, on_registry_request_callback) -> None:
        self._state_client_code = client_code
        self._state_ready = False
        self._restoring_tree = False
        self._tree_navigation: dict[str, Any] | None = None
        self._navigation_in_progress = False
        self._delete_parent_requests: dict[str, dict[str, str]] = {}
        super().__init__(
            parent,
            client_code=client_code,
            on_registry_request_callback=on_registry_request_callback,
        )

        state = self._SESSION_STATE.get(client_code) or {}
        favorites = state.get("favorites") or []
        self.session_favorites = [tuple(item) for item in favorites if len(item) == 3]
        self._state_ready = True

        # Let the initial context/list requests finish first, then restore the
        # user's Registry location and splitter position for this Dashboard run.
        self.after(650, self._restore_session_state)
        self.after(900, self._restore_sash_position)

    # ------------------------------------------------------------------
    # Build / activity state
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        super()._build_header()
        search_row = self.status_label.master
        self.activity_bar = ctk.CTkProgressBar(
            search_row,
            mode="indeterminate",
            height=3,
            fg_color=COLORS.surface_light,
            progress_color=COLORS.accent,
        )
        self.activity_bar.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=0,
            pady=(5, 0),
            sticky="ew",
        )
        self.activity_bar.grid_remove()

    def _build_explorer(self, frame) -> None:
        super()._build_explorer(frame)
        self.registry_panes.bind("<ButtonRelease-1>", self._remember_sash_position, add="+")

    def _set_busy(self, busy: bool) -> None:
        bar = getattr(self, "activity_bar", None)
        if bar is None:
            return
        if busy:
            bar.grid()
            try:
                bar.start()
            except Exception:
                pass
        else:
            try:
                bar.stop()
            except Exception:
                pass
            bar.grid_remove()

    def _sync_busy_state(self) -> None:
        self._set_busy(bool(self.pending))

    def _request(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> str:
        request_id = super()._request(operation, parameters, meta=meta)
        if not request_id:
            self._sync_busy_state()
            return ""

        if operation == "delete_key":
            parent = self._parent_scope(parameters or {})
            if parent:
                self._delete_parent_requests[request_id] = parent

        self._set_busy(True)
        return request_id

    def handle_progress(self, payload: dict[str, Any]) -> None:
        if payload.get("client_code") == self.client_code:
            self._set_busy(True)
        super().handle_progress(payload)

    def handle_result(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        operation = str(payload.get("operation") or "")
        pending_meta = dict(self.pending.get(request_id) or {})
        success = bool(payload.get("success"))

        super().handle_result(payload)

        if operation == "list_key" and success and pending_meta.get("purpose") == "tree_expand":
            self._continue_tree_navigation(str(pending_meta.get("tree_item") or ""))

        if operation == "delete_key" and not success:
            self._delete_parent_requests.pop(request_id, None)

        self.after_idle(self._sync_busy_state)

    # ------------------------------------------------------------------
    # Safe view/path navigation
    # ------------------------------------------------------------------

    def _on_view_changed(self) -> None:
        """Reload the whole visible tree cleanly when switching 32/64-bit view."""

        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        self._remember_state()
        self._start_tree_navigation(scope["hive"], scope["path"])

    def navigate_address(self) -> None:
        hive, path = self._parse_address(self.path_entry.get())
        if not hive:
            self._set_status("Invalid Registry address.", error=True)
            return
        self._start_tree_navigation(hive, path)

    def go_back(self) -> None:
        scope = self._current_scope()
        if not scope:
            return
        path = scope["path"].strip("\\")
        if not path:
            return
        parent = path.rsplit("\\", 1)[0] if "\\" in path else ""
        self._start_tree_navigation(scope["hive"], parent)

    def refresh_current_key(self) -> None:
        if self._navigation_in_progress:
            return
        super().refresh_current_key()

    def _on_tree_select(self, _event=None) -> None:
        if self._navigation_in_progress:
            selection = self.registry_tree.selection()
            if not selection:
                return
            item = selection[0]
            scope = self.tree_scope.get(item) or {}
            if scope.get("kind") == "key":
                self._selected_tree_item = item
                self._sync_scope_from_tree(item)
            return

        super()._on_tree_select(_event)
        self._remember_state()

    def _start_tree_navigation(self, hive: str, path: str) -> None:
        """Rebuild and navigate the lazy Regedit tree to a raw Registry path."""

        hive = str(hive or "HKLM")
        path = str(path or "").strip("\\")
        self._navigation_in_progress = True
        self._restoring_tree = True
        self._tree_navigation = None

        for item in self.values_tree.get_children():
            self.values_tree.delete(item)
        self.current_values.clear()

        try:
            self._insert_registry_roots()
            root_item = self._find_hive_root_item(hive)
            if not root_item:
                self._navigation_in_progress = False
                self._set_status(f"Registry hive not found: {hive}", error=True)
                return

            self.registry_tree.selection_set(root_item)
            self.registry_tree.focus(root_item)
            self._selected_tree_item = root_item
            self._sync_scope_from_tree(root_item)

            if not path:
                self._navigation_in_progress = False
                self._tree_navigation = None
                self.refresh_current_key()
                self._remember_state()
                return

            parts = [part for part in path.split("\\") if part]
            self._tree_navigation = {
                "hive": hive,
                "path": path,
                "parts": parts,
                "index": 0,
                "current_item": root_item,
            }
            self._set_status(f"Loading {hive}\\{path}...")
            self._load_tree_children(root_item, force=True)
        finally:
            self._restoring_tree = False

    def _continue_tree_navigation(self, expanded_item: str) -> None:
        nav = self._tree_navigation
        if not nav or not self._navigation_in_progress:
            return
        if expanded_item != nav.get("current_item"):
            return

        index = int(nav.get("index") or 0)
        parts = list(nav.get("parts") or [])
        if index >= len(parts):
            self._finish_tree_navigation()
            return

        wanted = str(parts[index])
        child_item = ""
        for child in self.registry_tree.get_children(expanded_item):
            if str(self.registry_tree.item(child, "text")).casefold() == wanted.casefold():
                child_item = child
                break

        if not child_item:
            # Direct access can still succeed even when the lazy tree could not
            # resolve a path component (permissions/race/change). Keep the raw
            # target in the address bar and let the backend report the result.
            self._navigation_in_progress = False
            self._tree_navigation = None
            self.active_scope = {"hive": str(nav["hive"]), "path": str(nav["path"])}
            self.hive_menu.set(str(nav["hive"]))
            self._show_address(str(nav["hive"]), str(nav["path"]))
            super().refresh_current_key()
            self._remember_state()
            return

        self.registry_tree.item(child_item, open=True)
        self.registry_tree.selection_set(child_item)
        self.registry_tree.focus(child_item)
        self._selected_tree_item = child_item
        self._sync_scope_from_tree(child_item)

        nav["index"] = index + 1
        nav["current_item"] = child_item

        if nav["index"] >= len(parts):
            self._finish_tree_navigation()
            return

        self._load_tree_children(child_item, force=True)

    def _finish_tree_navigation(self) -> None:
        self._navigation_in_progress = False
        self._tree_navigation = None
        super().refresh_current_key()
        self._remember_state()

    def _find_hive_root_item(self, hive: str) -> str:
        roots = self.registry_tree.get_children("")
        if not roots:
            return ""
        computer = roots[0]
        for item in self.registry_tree.get_children(computer):
            scope = self.tree_scope.get(item) or {}
            if scope.get("kind") == "key" and str(scope.get("hive")) == hive:
                return item
        return ""

    # ------------------------------------------------------------------
    # Delete-key parent recovery
    # ------------------------------------------------------------------

    @staticmethod
    def _parent_scope(parameters: dict[str, Any]) -> dict[str, str] | None:
        hive = str(parameters.get("hive") or "")
        if not hive:
            return None
        path = str(parameters.get("path") or "").strip("\\")
        parent = path.rsplit("\\", 1)[0] if "\\" in path else ""
        return {
            "hive": hive,
            "path": parent,
            "view": str(parameters.get("view") or "default"),
        }

    def _handle_mutation(self, payload: dict[str, Any]) -> None:
        if str(payload.get("operation") or "") != "delete_key":
            super()._handle_mutation(payload)
            self._remember_state()
            return

        request_id = str(payload.get("request_id") or "")
        parent = self._delete_parent_requests.pop(request_id, None)
        backup = payload.get("backup_id") or payload.get("pre_restore_backup_id")
        self._set_status(
            "delete_key completed." + (f" Backup: {backup}" if backup else "")
        )
        self.refresh_history()

        if parent:
            self.view_menu.set(parent["view"])
            self._start_tree_navigation(parent["hive"], parent["path"])
        else:
            self._start_tree_navigation("HKLM", "")

    # ------------------------------------------------------------------
    # Favorites + session state
    # ------------------------------------------------------------------

    def add_favorite(self) -> None:
        super().add_favorite()
        self._remember_state()

    def show_favorites(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Registry Favorites")
        window.geometry("820x460")
        window.minsize(640, 360)
        window.configure(fg_color=COLORS.background)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            window,
            text="Session Registry Favorites",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")

        wrap = ctk.CTkFrame(window, fg_color=COLORS.surface)
        wrap.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            wrap,
            columns=("hive", "path", "view"),
            show="headings",
            style=apply_treeview_style("Registry.Favorites.Treeview"),
            selectmode="browse",
        )
        tree.heading("hive", text="Hive")
        tree.heading("path", text="Path")
        tree.heading("view", text="View")
        tree.column("hive", width=100, anchor="w")
        tree.column("path", width=560, anchor="w")
        tree.column("view", width=80, anchor="center")
        tree.grid(row=0, column=0, sticky="nsew")

        scroll = ctk.CTkScrollbar(wrap, orientation="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)

        rows: dict[str, tuple[str, str, str]] = {}

        def reload_rows() -> None:
            for row in tree.get_children():
                tree.delete(row)
            rows.clear()
            for favorite in self.session_favorites:
                hive, path, view = favorite
                row = tree.insert("", "end", values=(hive, path or "(root)", view))
                rows[row] = favorite

        def selected_favorite() -> tuple[str, str, str] | None:
            selected = tree.selection()
            return rows.get(selected[0]) if selected else None

        def open_selected() -> None:
            favorite = selected_favorite()
            if not favorite:
                return
            hive, path, view = favorite
            self.view_menu.set(view)
            self._start_tree_navigation(hive, path)
            window.destroy()

        def remove_selected() -> None:
            favorite = selected_favorite()
            if not favorite:
                return
            self.session_favorites = [item for item in self.session_favorites if item != favorite]
            self._remember_state()
            reload_rows()

        def clear_all() -> None:
            if not self.session_favorites:
                return
            if not messagebox.askyesno("Clear Registry Favorites", "Clear all session Registry favorites?", parent=window):
                return
            self.session_favorites.clear()
            self._remember_state()
            reload_rows()

        tree.bind("<Double-1>", lambda _event: open_selected())
        reload_rows()

        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="ew")
        ctk.CTkButton(buttons, text="Open", command=open_selected, **primary_button_style()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(buttons, text="Remove", command=remove_selected, **secondary_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Clear all", command=clear_all, **danger_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Close", command=window.destroy, **secondary_button_style()).pack(side="right")

    def _remember_state(self) -> None:
        if not self._state_ready or self._restoring_tree:
            return
        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        state = self._SESSION_STATE.setdefault(self._state_client_code, {})
        state.update(
            {
                "hive": scope["hive"],
                "path": scope["path"],
                "view": self.view_menu.get() if hasattr(self, "view_menu") else "default",
                "favorites": [list(item) for item in self.session_favorites],
            }
        )
        sash = self._current_sash_position()
        if sash is not None:
            state["sash"] = sash

    def _restore_session_state(self) -> None:
        if not self.winfo_exists():
            return
        state = self._SESSION_STATE.get(self._state_client_code) or {}
        if not state:
            return
        view = str(state.get("view") or "default")
        if view in {"default", "64", "32"}:
            self.view_menu.set(view)
        hive = str(state.get("hive") or "HKLM")
        path = str(state.get("path") or "")
        self._start_tree_navigation(hive, path)

    def _current_sash_position(self) -> int | None:
        panes = getattr(self, "registry_panes", None)
        if panes is None:
            return None
        try:
            return int(panes.sash_coord(0)[0])
        except Exception:
            return None

    def _remember_sash_position(self, _event=None) -> None:
        self._remember_state()

    def _restore_sash_position(self) -> None:
        state = self._SESSION_STATE.get(self._state_client_code) or {}
        sash = state.get("sash")
        if sash is None:
            return
        try:
            self.registry_panes.sash_place(0, max(260, int(sash)), 0)
        except Exception:
            pass

    def destroy(self) -> None:
        self._remember_state()
        super().destroy()

    # ------------------------------------------------------------------
    # Safe .reg file browse + preview
    # ------------------------------------------------------------------

    @staticmethod
    def _read_reg_text_file(path: str | Path) -> str:
        data = Path(path).read_bytes()
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("cp1252")

    def open_import_dialog(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Safe .reg Import")
        window.geometry("900x650")
        window.minsize(720, 500)
        window.configure(fg_color=COLORS.background)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            window,
            text="Safe .reg Import",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        file_row = ctk.CTkFrame(window, fg_color="transparent")
        file_row.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        file_row.grid_columnconfigure(1, weight=1)
        file_label = ctk.CTkLabel(
            file_row,
            text="Paste content below or load a .reg file. Preview is required before Apply.",
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        )
        file_label.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        textbox = ctk.CTkTextbox(window, font=FONTS.mono_body)
        textbox.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="nsew")

        def load_file() -> None:
            path = filedialog.askopenfilename(
                parent=window,
                title="Open Registry File",
                filetypes=[("Registry files", "*.reg"), ("All files", "*.*")],
            )
            if not path:
                return
            try:
                text = self._read_reg_text_file(path)
            except Exception as exc:
                messagebox.showerror("Registry Import", f"Could not read file:\n{exc}", parent=window)
                return
            if len(text) > 2_000_000:
                messagebox.showerror(
                    "Registry Import",
                    "The .reg file is too large for safe preview (maximum 2,000,000 characters).",
                    parent=window,
                )
                return
            textbox.delete("1.0", "end")
            textbox.insert("1.0", text)
            self._last_import_text = ""
            file_label.configure(text=str(Path(path).name))

        ctk.CTkButton(
            file_row,
            text="Browse .reg",
            width=120,
            command=load_file,
            **secondary_button_style(),
        ).grid(row=0, column=0)

        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="ew")

        def preview() -> None:
            text = textbox.get("1.0", "end-1c")
            if not text.strip():
                messagebox.showwarning("Registry Import", "Load or paste .reg content first.", parent=window)
                return
            if len(text) > 2_000_000:
                messagebox.showerror("Registry Import", "The .reg content exceeds the safe preview size limit.", parent=window)
                return
            self._last_import_text = text
            self._request("import_reg_preview", {"reg_text": text, "view": self.view_menu.get()})

        def apply() -> None:
            text = textbox.get("1.0", "end-1c")
            if not text or text != self._last_import_text:
                messagebox.showwarning(
                    "Preview required",
                    "Run Preview after the last edit before applying.",
                    parent=window,
                )
                return
            answer = ctk.CTkInputDialog(
                text=(
                    "Type IMPORT to apply the previewed .reg changes.\n"
                    "Automatic backups will be created before writes."
                ),
                title="Confirm Registry Import",
            ).get_input()
            if answer == "IMPORT":
                self._request("import_reg_apply", {"reg_text": text, "view": self.view_menu.get()})

        ctk.CTkButton(buttons, text="Preview", command=preview, **primary_button_style()).pack(side="left", padx=(0, 6))
        ctk.CTkButton(buttons, text="Apply", command=apply, **danger_button_style()).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="Close", command=window.destroy, **secondary_button_style()).pack(side="right")

    # ------------------------------------------------------------------
    # Context menus / More menu
    # ------------------------------------------------------------------

    def _show_more_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Export selected key...", command=self.export_current)
        menu.add_command(label="Import .reg...", command=self.open_import_dialog)
        menu.add_separator()
        menu.add_command(label="Copy key name", command=self.copy_current_key_name)
        menu.add_command(label="Add current key to favorites", command=self.add_favorite)
        menu.add_command(label="Open favorites...", command=self.show_favorites)
        menu.add_separator()
        menu.add_command(label="Registry diagnostics", command=self.run_diagnostics)
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

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
        menu.add_command(label="Create Snapshot", command=self.create_snapshot)
        menu.add_command(label="Export", command=self.export_current)
        menu.add_command(label="Add to Favorites", command=self.add_favorite)
        menu.add_command(label="Open Favorites", command=self.show_favorites)
        if scope.get("path"):
            menu.add_separator()
            menu.add_command(label="Delete", command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="Copy Key Name", command=self.copy_current_key_name)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_value_context_menu(self, event) -> None:
        item = self.values_tree.identify_row(event.y)
        if item:
            self.values_tree.selection_set(item)
            self.values_tree.focus(item)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Modify", command=self.edit_value)
        menu.add_command(label="New Value", command=self.create_value)
        menu.add_separator()
        menu.add_command(label="Delete", command=self.delete_selected)
        menu.add_separator()
        menu.add_command(label="Copy Name", command=self.copy_selected_value_name)
        menu.add_command(label="Copy Data", command=self.copy_selected_value_data)
        menu.add_separator()
        menu.add_command(label="Create Profile from Value", command=self.create_profile_from_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
