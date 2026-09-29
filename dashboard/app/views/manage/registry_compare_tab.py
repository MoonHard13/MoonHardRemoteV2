"""Registry Compare Center for MoonHard Dashboard."""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
from tkinter import filedialog, ttk

from app.ui.theme import (
    COLORS,
    FONTS,
    apply_treeview_style,
    card_style,
    primary_button_style,
    secondary_button_style,
)
from app.views.manage.registry_polished_navigation import PolishedRegistryTab


class RegistryCompareTab(PolishedRegistryTab):
    """Adds unified Current/Snapshot/Profile/PC comparison to Registry Center."""

    MODES = (
        "Current vs Snapshot",
        "Current vs Profile",
        "PC vs PC",
    )

    FILTERS = (
        "Differences",
        "All",
        "Same",
        "Different",
        "Missing",
        "Extra",
    )

    def __init__(
        self,
        parent,
        *,
        client_code: str,
        on_registry_request_callback,
        get_compare_clients_callback: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.get_compare_clients_callback = get_compare_clients_callback
        self._compare_snapshot_rows: dict[str, dict[str, Any]] = {}
        self._compare_profile_rows: dict[str, dict[str, Any]] = {}
        self._compare_client_rows: dict[str, dict[str, Any]] = {}
        self._compare_results: list[dict[str, Any]] = []
        self._compare_summary = {"same": 0, "different": 0, "missing": 0, "extra": 0}
        self._compare_batches: dict[str, dict[str, Any]] = {}
        self._compare_scope_label = None
        self._compare_warning_label = None
        super().__init__(
            parent,
            client_code=client_code,
            on_registry_request_callback=on_registry_request_callback,
        )
        self.after(900, self._refresh_compare_sources)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_sections(self) -> None:
        super()._build_sections()
        frame = self.sections.add("Compare")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)
        self._build_compare(frame)

    def _build_compare(self, frame) -> None:
        header = ctk.CTkFrame(frame, **card_style())
        header.grid(row=0, column=0, pady=(6, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Registry Compare",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=(16, 12), pady=(13, 3), sticky="w")

        self.compare_mode_menu = ctk.CTkOptionMenu(
            header,
            values=list(self.MODES),
            width=220,
            height=34,
            command=lambda _value: self._on_compare_mode_changed(),
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.compare_mode_menu.grid(row=0, column=1, padx=(0, 8), pady=(12, 3), sticky="e")
        self.compare_mode_menu.set(self.MODES[0])

        ctk.CTkButton(
            header,
            text="Run Compare",
            width=130,
            height=34,
            command=self.run_compare,
            **primary_button_style(),
        ).grid(row=0, column=2, padx=(0, 16), pady=(12, 3), sticky="e")

        ctk.CTkLabel(
            header,
            text=(
                "Compare the selected Registry scope against a previous snapshot, "
                "a known-good profile, or another connected PC."
            ),
            font=FONTS.small,
            text_color=COLORS.text_secondary,
            anchor="w",
        ).grid(row=1, column=0, columnspan=3, padx=16, pady=(0, 8), sticky="ew")

        self._compare_scope_label = ctk.CTkLabel(
            header,
            text="",
            font=FONTS.small,
            text_color=COLORS.info,
            fg_color=COLORS.info_soft,
            corner_radius=8,
            height=28,
            anchor="w",
        )
        self._compare_scope_label.grid(
            row=2, column=0, columnspan=3, padx=16, pady=(0, 13), sticky="ew"
        )

        source_card = ctk.CTkFrame(frame, **card_style())
        source_card.grid(row=1, column=0, pady=(0, 8), sticky="ew")
        source_card.grid_columnconfigure(0, weight=1)

        self.compare_snapshot_frame = ctk.CTkFrame(source_card, fg_color="transparent")
        self.compare_snapshot_frame.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        self.compare_snapshot_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.compare_snapshot_frame,
            text="Baseline snapshot",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.compare_snapshot_menu = ctk.CTkOptionMenu(
            self.compare_snapshot_frame,
            values=["No snapshots loaded"],
            width=580,
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.compare_snapshot_menu.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        ctk.CTkButton(
            self.compare_snapshot_frame,
            text="Refresh",
            width=90,
            command=self._load_compare_snapshots,
            **secondary_button_style(),
        ).grid(row=0, column=2)

        self.compare_profile_frame = ctk.CTkFrame(source_card, fg_color="transparent")
        self.compare_profile_frame.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        self.compare_profile_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.compare_profile_frame,
            text="Known-good profile",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.compare_profile_menu = ctk.CTkOptionMenu(
            self.compare_profile_frame,
            values=["No profiles loaded"],
            width=580,
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.compare_profile_menu.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        ctk.CTkButton(
            self.compare_profile_frame,
            text="Refresh",
            width=90,
            command=self._load_compare_profiles,
            **secondary_button_style(),
        ).grid(row=0, column=2)

        self.compare_pc_frame = ctk.CTkFrame(source_card, fg_color="transparent")
        self.compare_pc_frame.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        self.compare_pc_frame.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(
            self.compare_pc_frame,
            text=f"Source PC: {self.client_code}",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=0, padx=(0, 14), sticky="w")
        ctk.CTkLabel(
            self.compare_pc_frame,
            text="Target PC",
            font=FONTS.body_bold,
            text_color=COLORS.text_primary,
        ).grid(row=0, column=1, padx=(0, 8), sticky="w")
        self.compare_pc_menu = ctk.CTkOptionMenu(
            self.compare_pc_frame,
            values=["No connected PCs"],
            width=420,
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.compare_pc_menu.grid(row=0, column=2, padx=(0, 8), sticky="ew")
        ctk.CTkButton(
            self.compare_pc_frame,
            text="Refresh PCs",
            width=110,
            command=self._refresh_compare_clients,
            **secondary_button_style(),
        ).grid(row=0, column=3)

        summary = ctk.CTkFrame(frame, **card_style())
        summary.grid(row=2, column=0, pady=(0, 8), sticky="ew")
        summary.grid_columnconfigure(5, weight=1)

        self.compare_same_label = self._summary_badge(summary, "Same  0", COLORS.success, COLORS.success_soft, 0)
        self.compare_different_label = self._summary_badge(summary, "Different  0", COLORS.warning, COLORS.warning_soft, 1)
        self.compare_missing_label = self._summary_badge(summary, "Missing  0", COLORS.danger, COLORS.danger_soft, 2)
        self.compare_extra_label = self._summary_badge(summary, "Extra  0", COLORS.info, COLORS.info_soft, 3)

        self._compare_warning_label = ctk.CTkLabel(
            summary,
            text="",
            font=FONTS.small,
            text_color=COLORS.warning,
            anchor="w",
        )
        self._compare_warning_label.grid(row=0, column=4, padx=(10, 6), pady=10, sticky="w")

        self.compare_filter_menu = ctk.CTkOptionMenu(
            summary,
            values=list(self.FILTERS),
            width=135,
            command=lambda _value: self._render_compare_results(),
            dynamic_resizing=False,
            fg_color=COLORS.surface_light,
            button_color=COLORS.accent,
            button_hover_color=COLORS.accent_hover,
            text_color=COLORS.text_primary,
            dropdown_fg_color=COLORS.surface,
            dropdown_hover_color=COLORS.surface_hover,
        )
        self.compare_filter_menu.set("Differences")
        self.compare_filter_menu.grid(row=0, column=6, padx=(4, 8), pady=10)

        self.compare_search_entry = ctk.CTkEntry(
            summary,
            width=260,
            placeholder_text="Filter path / value / data...",
        )
        self.compare_search_entry.grid(row=0, column=7, padx=(0, 8), pady=10)
        self.compare_search_entry.bind("<KeyRelease>", lambda _event: self._render_compare_results())

        ctk.CTkButton(
            summary,
            text="Export",
            width=88,
            command=self.export_compare_results,
            **secondary_button_style(),
        ).grid(row=0, column=8, padx=(0, 12), pady=10)

        result_card = ctk.CTkFrame(frame, **card_style())
        result_card.grid(row=3, column=0, sticky="nsew")
        result_card.grid_columnconfigure(0, weight=1)
        result_card.grid_rowconfigure(1, weight=1)

        result_top = ctk.CTkFrame(result_card, fg_color="transparent")
        result_top.grid(row=0, column=0, columnspan=2, padx=14, pady=(10, 7), sticky="ew")
        result_top.grid_columnconfigure(0, weight=1)
        self.compare_result_title = ctk.CTkLabel(
            result_top,
            text="Differences",
            font=FONTS.section_title,
            text_color=COLORS.text_primary,
            anchor="w",
        )
        self.compare_result_title.grid(row=0, column=0, sticky="w")
        self.compare_result_count = ctk.CTkLabel(
            result_top,
            text="0 rows",
            font=FONTS.small,
            text_color=COLORS.text_muted,
            anchor="e",
        )
        self.compare_result_count.grid(row=0, column=1, sticky="e")

        style = apply_treeview_style("Registry.Compare.Treeview")
        self.compare_tree = ttk.Treeview(
            result_card,
            columns=("status", "kind", "path", "name", "left", "right"),
            show="headings",
            style=style,
            selectmode="browse",
        )
        headings = (
            ("status", "Status", 100),
            ("kind", "Kind", 70),
            ("path", "Path", 360),
            ("name", "Name", 180),
            ("left", "Baseline / Source", 330),
            ("right", "Current / Target", 330),
        )
        for column, title, width in headings:
            self.compare_tree.heading(column, text=title)
            self.compare_tree.column(column, width=width, minwidth=70, anchor="w")
        self.compare_tree.grid(row=1, column=0, sticky="nsew")
        self.compare_tree.bind("<Double-1>", self._open_compare_result_in_explorer)

        y_scroll = ctk.CTkScrollbar(
            result_card,
            orientation="vertical",
            command=self.compare_tree.yview,
        )
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll = ctk.CTkScrollbar(
            result_card,
            orientation="horizontal",
            command=self.compare_tree.xview,
        )
        x_scroll.grid(row=2, column=0, sticky="ew")
        self.compare_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.compare_snapshot_frame.grid()
        self.compare_profile_frame.grid_remove()
        self.compare_pc_frame.grid_remove()
        self._update_compare_scope_label()

    def _summary_badge(self, parent, text: str, color: str, background: str, column: int):
        label = ctk.CTkLabel(
            parent,
            text=text,
            font=FONTS.small,
            text_color=color,
            fg_color=background,
            corner_radius=8,
            height=28,
        )
        label.grid(row=0, column=column, padx=(12 if column == 0 else 4, 4), pady=10)
        return label

    # ------------------------------------------------------------------
    # Source loading / mode
    # ------------------------------------------------------------------

    def _on_compare_mode_changed(self) -> None:
        mode = self.compare_mode_menu.get()
        self.compare_snapshot_frame.grid_remove()
        self.compare_profile_frame.grid_remove()
        self.compare_pc_frame.grid_remove()
        if mode == "Current vs Snapshot":
            self.compare_snapshot_frame.grid()
            self.compare_tree.heading("left", text="Snapshot")
            self.compare_tree.heading("right", text="Current")
            self._load_compare_snapshots()
        elif mode == "Current vs Profile":
            self.compare_profile_frame.grid()
            self.compare_tree.heading("left", text="Expected")
            self.compare_tree.heading("right", text="Current")
            self._load_compare_profiles()
        else:
            self.compare_pc_frame.grid()
            self.compare_tree.heading("left", text=f"Source · {self.client_code}")
            self.compare_tree.heading("right", text="Target PC")
            self._refresh_compare_clients()
        self._update_compare_scope_label()

    def _refresh_compare_sources(self) -> None:
        if not hasattr(self, "compare_mode_menu"):
            return
        mode = self.compare_mode_menu.get()
        if mode == "Current vs Snapshot":
            self._load_compare_snapshots()
        elif mode == "Current vs Profile":
            self._load_compare_profiles()
        else:
            self._refresh_compare_clients()

    def _load_compare_snapshots(self) -> None:
        self._compare_request(
            "history",
            {"limit": 300},
            target_client_code=self.client_code,
            purpose="snapshot_list",
        )

    def _load_compare_profiles(self) -> None:
        self._compare_request(
            "profile_list",
            {},
            target_client_code=self.client_code,
            purpose="profile_list",
        )

    def _refresh_compare_clients(self) -> None:
        rows = []
        if callable(self.get_compare_clients_callback):
            try:
                rows = list(self.get_compare_clients_callback() or [])
            except Exception:
                rows = []

        mapping: dict[str, dict[str, Any]] = {}
        for client in rows:
            code = str(client.get("client_code") or "").strip()
            if not code or code == self.client_code or not bool(client.get("ws_connected", False)):
                continue
            name = str(client.get("display_name") or client.get("pc_name") or code)
            pc_name = str(client.get("pc_name") or "")
            label = f"{name} · {pc_name} · {code}" if pc_name and pc_name != name else f"{name} · {code}"
            mapping[label] = dict(client)

        self._compare_client_rows = mapping
        values = list(mapping) or ["No connected PCs"]
        self.compare_pc_menu.configure(values=values)
        self.compare_pc_menu.set(values[0])

    def _update_compare_scope_label(self) -> None:
        if self._compare_scope_label is None:
            return
        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        path = scope.get("path") or "(root)"
        view = self.view_menu.get() if hasattr(self, "view_menu") else "default"
        self._compare_scope_label.configure(
            text=f"Explorer scope  ·  {scope.get('hive')}\\{path}  ·  view {view}"
        )

    def _sync_scope_from_tree(self, item: str) -> None:
        super()._sync_scope_from_tree(item)
        self._update_compare_scope_label()

    # ------------------------------------------------------------------
    # Requests / routing
    # ------------------------------------------------------------------

    def _compare_request(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        target_client_code: str,
        purpose: str,
        batch_id: str = "",
    ) -> str:
        request_id = str(uuid.uuid4())
        payload = {
            "type": "registry_request",
            "request_id": request_id,
            "client_code": target_client_code,
            "operation": operation,
            "parameters": parameters,
        }
        self.pending[request_id] = {
            "operation": operation,
            "compare_request": True,
            "compare_purpose": purpose,
            "compare_batch": batch_id,
            "target_client_code": target_client_code,
        }
        self._set_busy(True)
        self._set_status(f"Compare: {operation} on {target_client_code}...")
        try:
            sent = self.on_registry_request_callback(payload)
        except Exception as exc:
            sent = False
            self._set_status(str(exc), error=True)
        if sent is False:
            self.pending.pop(request_id, None)
            self._set_status(
                f"Registry Compare request was not sent to {target_client_code}.",
                error=True,
            )
            self._sync_busy_state()
            return ""
        return request_id

    def handle_progress(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        meta = self.pending.get(request_id) or {}
        if meta.get("compare_request"):
            self._set_busy(True)
            message = str(payload.get("message") or "Comparing Registry...")
            current = payload.get("current")
            total = payload.get("total")
            suffix = f" ({current}/{total})" if current is not None and total else ""
            self._set_status(message + suffix)
            return
        super().handle_progress(payload)

    def handle_result(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        meta = dict(self.pending.get(request_id) or {})
        if not meta.get("compare_request"):
            super().handle_result(payload)
            return

        self.pending.pop(request_id, None)
        purpose = str(meta.get("compare_purpose") or "")
        batch_id = str(meta.get("compare_batch") or "")
        if not payload.get("success"):
            if batch_id and batch_id in self._compare_batches:
                self._compare_batches[batch_id]["failed"] = True
            self._set_status(
                f"Compare failed on {payload.get('client_code')}: {payload.get('error') or 'Registry operation failed.'}",
                error=True,
            )
            self.after_idle(self._sync_busy_state)
            return

        if purpose == "snapshot_list":
            self._handle_compare_snapshot_list(payload)
        elif purpose == "profile_list":
            self._handle_compare_profile_list(payload)
        elif purpose == "snapshot_compare":
            self._handle_snapshot_compare_result(payload)
        elif purpose == "profile_compare":
            self._handle_profile_compare_result(payload)
        elif purpose in {"pc_left", "pc_right"}:
            batch = self._compare_batches.get(batch_id)
            if batch is not None:
                batch["left" if purpose == "pc_left" else "right"] = dict(payload)
                if batch.get("left") is not None and batch.get("right") is not None:
                    self._finish_pc_compare(batch_id)

        self.after_idle(self._sync_busy_state)

    # ------------------------------------------------------------------
    # Compare execution
    # ------------------------------------------------------------------

    def run_compare(self) -> None:
        self._update_compare_scope_label()
        mode = self.compare_mode_menu.get()
        if mode == "Current vs Snapshot":
            row = self._compare_snapshot_rows.get(self.compare_snapshot_menu.get())
            if not row:
                self._set_status("Select a Registry snapshot first.", error=True)
                return
            self._compare_request(
                "compare_snapshot",
                {"backup_id": row["backup_id"]},
                target_client_code=self.client_code,
                purpose="snapshot_compare",
            )
            return

        if mode == "Current vs Profile":
            row = self._compare_profile_rows.get(self.compare_profile_menu.get())
            if not row:
                self._set_status("Select a Registry profile first.", error=True)
                return
            self._compare_request(
                "profile_check",
                {"profile_id": row["profile_id"]},
                target_client_code=self.client_code,
                purpose="profile_compare",
            )
            return

        target = self._compare_client_rows.get(self.compare_pc_menu.get())
        if not target:
            self._set_status("Select a connected target PC first.", error=True)
            return
        target_code = str(target.get("client_code") or "")
        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        params = {
            "hive": scope["hive"],
            "path": scope["path"],
            "view": self.view_menu.get(),
            "max_entries": 10000,
        }
        batch_id = str(uuid.uuid4())
        self._compare_batches[batch_id] = {
            "left": None,
            "right": None,
            "failed": False,
            "target_code": target_code,
        }
        left_request = self._compare_request(
            "capture_scope",
            params,
            target_client_code=self.client_code,
            purpose="pc_left",
            batch_id=batch_id,
        )
        right_request = self._compare_request(
            "capture_scope",
            params,
            target_client_code=target_code,
            purpose="pc_right",
            batch_id=batch_id,
        )
        if not left_request or not right_request:
            self._compare_batches[batch_id]["failed"] = True

    def _handle_compare_snapshot_list(self, payload: dict[str, Any]) -> None:
        mapping: dict[str, dict[str, Any]] = {}
        for item in payload.get("items") or []:
            backup_id = str(item.get("backup_id") or "")
            if not backup_id:
                continue
            created = str(item.get("created_at") or "")[:19].replace("T", " ")
            reason = str(item.get("reason") or "snapshot")
            hive = str(item.get("hive") or "")
            path = str(item.get("path") or "(root)") or "(root)"
            view = str(item.get("view") or "default")
            label = f"{created} · {reason} · {hive}\\{path} · {view} · {backup_id[:8]}"
            mapping[label] = dict(item)
        self._compare_snapshot_rows = mapping
        values = list(mapping) or ["No snapshots available"]
        self.compare_snapshot_menu.configure(values=values)
        self.compare_snapshot_menu.set(values[0])
        self._set_status(f"Loaded {len(mapping)} Registry snapshots/backups for Compare.")

    def _handle_compare_profile_list(self, payload: dict[str, Any]) -> None:
        mapping: dict[str, dict[str, Any]] = {}
        for profile in payload.get("profiles") or []:
            profile_id = str(profile.get("profile_id") or "")
            if not profile_id:
                continue
            label = f"{profile.get('name') or 'Unnamed'} · {profile.get('entry_count', 0)} entries · {profile_id[:8]}"
            mapping[label] = dict(profile)
        self._compare_profile_rows = mapping
        values = list(mapping) or ["No profiles available"]
        self.compare_profile_menu.configure(values=values)
        self.compare_profile_menu.set(values[0])
        self._set_status(f"Loaded {len(mapping)} Registry profiles for Compare.")

    def _handle_snapshot_compare_result(self, payload: dict[str, Any]) -> None:
        results: list[dict[str, Any]] = []
        for item in payload.get("removed") or []:
            path, name, kind = self._identity_parts(str(item.get("identity") or ""))
            before = item.get("before")
            results.append(self._compare_row("Missing", kind, path, name, before, None))
        for item in payload.get("added") or []:
            path, name, kind = self._identity_parts(str(item.get("identity") or ""))
            current = item.get("current")
            results.append(self._compare_row("Extra", kind, path, name, None, current))
        for item in payload.get("changed") or []:
            path, name, kind = self._identity_parts(str(item.get("identity") or ""))
            results.append(
                self._compare_row(
                    "Different",
                    kind,
                    path,
                    name,
                    item.get("before"),
                    item.get("current"),
                )
            )
        self._compare_results = results
        self._compare_summary = {
            "same": int(payload.get("same_count") or 0),
            "different": len(payload.get("changed") or []),
            "missing": len(payload.get("removed") or []),
            "extra": len(payload.get("added") or []),
        }
        self._apply_compare_summary(bool(payload.get("truncated")))
        self._render_compare_results()
        self._set_status(
            f"Snapshot compare completed: {payload.get('different_count', 0)} differences."
        )

    def _handle_profile_compare_result(self, payload: dict[str, Any]) -> None:
        results: list[dict[str, Any]] = []
        counts = {"same": 0, "different": 0, "missing": 0, "extra": 0}
        for item in payload.get("results") or []:
            status_raw = str(item.get("status") or "different")
            status = {"ok": "Same", "missing": "Missing", "different": "Different"}.get(
                status_raw,
                "Different",
            )
            key = status.lower()
            counts[key] = counts.get(key, 0) + 1
            path, name = self._profile_identity_parts(str(item.get("identity") or ""))
            results.append(
                self._compare_row(
                    status,
                    "Value",
                    path,
                    name,
                    item.get("expected"),
                    item.get("current"),
                )
            )
        self._compare_results = results
        self._compare_summary = counts
        self._apply_compare_summary(False)
        self._render_compare_results()
        self._set_status(
            f"Profile compare completed: {payload.get('problem_count', 0)} differences."
        )

    def _finish_pc_compare(self, batch_id: str) -> None:
        batch = self._compare_batches.pop(batch_id, None)
        if not batch or batch.get("failed"):
            return
        left = dict(batch.get("left") or {})
        right = dict(batch.get("right") or {})
        results, summary = self.compare_capture_payloads(left, right)
        self._compare_results = results
        self._compare_summary = summary
        truncated = bool(left.get("truncated")) or bool(right.get("truncated"))
        self._apply_compare_summary(truncated)
        target_code = str(batch.get("target_code") or "Target")
        self.compare_tree.heading("left", text=f"Source · {self.client_code}")
        self.compare_tree.heading("right", text=f"Target · {target_code}")
        self._render_compare_results()
        total_diff = summary["different"] + summary["missing"] + summary["extra"]
        self._set_status(f"PC Registry compare completed: {total_diff} differences.")

    # ------------------------------------------------------------------
    # Diff engine / rendering
    # ------------------------------------------------------------------

    @classmethod
    def compare_capture_payloads(
        cls,
        left_payload: dict[str, Any],
        right_payload: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        left_flat = cls._flatten_capture(left_payload)
        right_flat = cls._flatten_capture(right_payload)
        results: list[dict[str, Any]] = []
        counts = {"same": 0, "different": 0, "missing": 0, "extra": 0}

        all_ids = sorted(set(left_flat) | set(right_flat))
        for identity in all_ids:
            left = left_flat.get(identity)
            right = right_flat.get(identity)
            if left is None:
                status = "Extra"
                source = right or {}
            elif right is None:
                status = "Missing"
                source = left
            elif left.get("canonical") == right.get("canonical"):
                status = "Same"
                source = left
            else:
                status = "Different"
                source = left
            counts[status.lower()] += 1
            results.append(
                cls._compare_row(
                    status,
                    str(source.get("kind") or "Value"),
                    str(source.get("path") or ""),
                    str(source.get("name") or ""),
                    None if left is None else left.get("canonical"),
                    None if right is None else right.get("canonical"),
                )
            )
        return results, counts

    @classmethod
    def _flatten_capture(cls, payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not bool(payload.get("exists", True)):
            return {}
        tree = payload.get("tree") or {}
        base_path = str(payload.get("path") or "")
        flat: dict[str, dict[str, Any]] = {}

        def walk(node: dict[str, Any], path: str) -> None:
            key_identity = f"K|{path}"
            flat[key_identity] = {
                "kind": "Key",
                "path": path,
                "name": "",
                "canonical": "key",
            }
            for value in node.get("values") or []:
                name = str(value.get("name") or "")
                identity = f"V|{path}|{name}"
                flat[identity] = {
                    "kind": "Value",
                    "path": path,
                    "name": name,
                    "canonical": {
                        "type": value.get("type"),
                        "data": value.get("data"),
                    },
                }
            for child, child_tree in (node.get("subkeys") or {}).items():
                if not isinstance(child_tree, dict):
                    continue
                child_path = f"{path}\\{child}" if path else str(child)
                walk(child_tree, child_path)

        walk(tree, base_path)
        return flat

    @staticmethod
    def _compare_row(
        status: str,
        kind: str,
        path: str,
        name: str,
        left: Any,
        right: Any,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "kind": kind,
            "path": path,
            "name": name or ("(Default)" if kind == "Value" else ""),
            "left_raw": left,
            "right_raw": right,
            "left": RegistryCompareTab._display_compare_value(left),
            "right": RegistryCompareTab._display_compare_value(right),
        }

    @staticmethod
    def _display_compare_value(value: Any) -> str:
        if value is None:
            return "—"
        if value == "key":
            return "Key exists"
        if isinstance(value, dict) and "type" in value:
            data = value.get("data")
            if isinstance(data, dict) and data.get("encoding") == "base64":
                data_text = f"<binary {data.get('length', '?')} bytes>"
            elif isinstance(data, list):
                data_text = " | ".join(str(part) for part in data)
            else:
                data_text = str(data)
            text = f"{value.get('type')}: {data_text}"
        else:
            text = str(value)
        return text if len(text) <= 500 else text[:497] + "..."

    @staticmethod
    def _identity_parts(identity: str) -> tuple[str, str, str]:
        if identity.startswith("K|"):
            return identity[2:], "", "Key"
        if identity.startswith("V|"):
            body = identity[2:]
            if "|" in body:
                path, name = body.rsplit("|", 1)
                return path, name, "Value"
            return body, "", "Value"
        return identity, "", "Value"

    @staticmethod
    def _profile_identity_parts(identity: str) -> tuple[str, str]:
        parts = identity.split("|", 3)
        if len(parts) == 4:
            return parts[2], parts[3]
        return identity, ""

    def _apply_compare_summary(self, truncated: bool) -> None:
        summary = self._compare_summary
        self.compare_same_label.configure(text=f"Same  {summary.get('same', 0)}")
        self.compare_different_label.configure(text=f"Different  {summary.get('different', 0)}")
        self.compare_missing_label.configure(text=f"Missing  {summary.get('missing', 0)}")
        self.compare_extra_label.configure(text=f"Extra  {summary.get('extra', 0)}")
        self._compare_warning_label.configure(
            text="Results truncated by safe capture limit" if truncated else ""
        )

    def _render_compare_results(self) -> None:
        if not hasattr(self, "compare_tree"):
            return
        for item in self.compare_tree.get_children():
            self.compare_tree.delete(item)

        filter_mode = self.compare_filter_menu.get()
        query = self.compare_search_entry.get().strip().casefold()
        visible = []
        for row in self._compare_results:
            status = str(row.get("status") or "")
            if filter_mode == "Differences" and status == "Same":
                continue
            if filter_mode not in {"All", "Differences"} and status != filter_mode:
                continue
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("status", "kind", "path", "name", "left", "right")
            ).casefold()
            if query and query not in haystack:
                continue
            visible.append(row)

        for row in visible:
            self.compare_tree.insert(
                "",
                "end",
                values=(
                    row.get("status"),
                    row.get("kind"),
                    row.get("path"),
                    row.get("name"),
                    row.get("left"),
                    row.get("right"),
                ),
            )

        self.compare_result_title.configure(text=filter_mode)
        self.compare_result_count.configure(text=f"{len(visible)} rows")

    def _open_compare_result_in_explorer(self, _event=None) -> None:
        selected = self.compare_tree.selection()
        if not selected:
            return
        values = self.compare_tree.item(selected[0], "values")
        if len(values) < 3:
            return
        path = str(values[2] or "")
        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        self.sections.set("Explorer")
        self._start_tree_navigation(scope["hive"], path)

    def export_compare_results(self) -> None:
        if not self._compare_results:
            self._set_status("Run a Registry comparison before exporting.", error=True)
            return
        path = filedialog.asksaveasfilename(
            title="Export Registry Compare",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() == ".json":
            target.write_text(
                json.dumps(
                    {
                        "summary": self._compare_summary,
                        "results": self._compare_results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            with target.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("status", "kind", "path", "name", "left", "right"),
                )
                writer.writeheader()
                for row in self._compare_results:
                    writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
        self._set_status(f"Registry Compare exported: {target}")
