"""Final guard layer for Registry Compare Center."""

from __future__ import annotations

from typing import Any

from app.views.manage.registry_compare_tab import RegistryCompareTab as _BaseRegistryCompareTab


class RegistryCompareTab(_BaseRegistryCompareTab):
    """Keeps compare scope messaging accurate and cleans failed PC compare batches."""

    def _build_compare(self, frame) -> None:
        super()._build_compare(frame)
        self.compare_snapshot_menu.configure(
            command=lambda _value: self._update_compare_scope_label()
        )
        self.compare_profile_menu.configure(
            command=lambda _value: self._update_compare_scope_label()
        )

    def _on_compare_mode_changed(self) -> None:
        super()._on_compare_mode_changed()
        self._update_compare_scope_label()

    def _handle_compare_snapshot_list(self, payload: dict[str, Any]) -> None:
        super()._handle_compare_snapshot_list(payload)
        self._update_compare_scope_label()

    def _handle_compare_profile_list(self, payload: dict[str, Any]) -> None:
        super()._handle_compare_profile_list(payload)
        self._update_compare_scope_label()

    def _update_compare_scope_label(self) -> None:
        label = getattr(self, "_compare_scope_label", None)
        if label is None:
            return

        mode_menu = getattr(self, "compare_mode_menu", None)
        mode = mode_menu.get() if mode_menu is not None else "PC vs PC"
        if mode == "Current vs Snapshot":
            menu = getattr(self, "compare_snapshot_menu", None)
            row = self._compare_snapshot_rows.get(menu.get()) if menu is not None else None
            if row:
                path = str(row.get("path") or "(root)") or "(root)"
                label.configure(
                    text=(
                        f"Snapshot scope  ·  {row.get('hive')}\\{path}  ·  "
                        f"view {row.get('view') or 'default'}"
                    )
                )
            else:
                label.configure(text="Snapshot scope  ·  select a baseline snapshot")
            return

        if mode == "Current vs Profile":
            label.configure(
                text="Profile scope  ·  each profile entry is checked against its exact hive / path / view"
            )
            return

        scope = self._current_scope() or {"hive": "HKLM", "path": ""}
        path = scope.get("path") or "(root)"
        view = self.view_menu.get() if hasattr(self, "view_menu") else "default"
        label.configure(
            text=f"PC compare scope  ·  {scope.get('hive')}\\{path}  ·  view {view}"
        )

    def run_compare(self) -> None:
        super().run_compare()
        # A send failure is known synchronously. Do not leave an unreachable
        # half-batch waiting forever for its second capture.
        for batch_id, batch in list(self._compare_batches.items()):
            if batch.get("failed"):
                self._compare_batches.pop(batch_id, None)

    def handle_result(self, payload: dict[str, Any]) -> None:
        request_id = str(payload.get("request_id") or "")
        meta = dict(self.pending.get(request_id) or {})
        batch_id = str(meta.get("compare_batch") or "")
        compare_request = bool(meta.get("compare_request"))
        success = bool(payload.get("success"))

        super().handle_result(payload)

        if compare_request and batch_id and not success:
            self._compare_batches.pop(batch_id, None)

    def _open_compare_result_in_explorer(self, _event=None) -> None:
        selected = self.compare_tree.selection()
        if not selected:
            return
        values = self.compare_tree.item(selected[0], "values")
        if len(values) < 3:
            return
        path = str(values[2] or "")
        mode = self.compare_mode_menu.get()

        if mode == "Current vs Snapshot":
            row = self._compare_snapshot_rows.get(self.compare_snapshot_menu.get())
            hive = str((row or {}).get("hive") or "")
            if not hive:
                return
            self.sections.set("Explorer")
            self._start_tree_navigation(hive, path)
            return

        if mode == "PC vs PC":
            scope = self._current_scope() or {"hive": "HKLM", "path": ""}
            self.sections.set("Explorer")
            self._start_tree_navigation(scope["hive"], path)
            return

        self._set_status(
            "Profile Compare can span multiple hives; open the exact entry from the Profiles result instead."
        )
