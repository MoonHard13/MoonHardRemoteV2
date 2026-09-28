"""Navigation guard for the polished Registry tree."""

from __future__ import annotations

from typing import Any

from app.views.manage.registry_polished_tab import PolishedRegistryTab as _BasePolishedRegistryTab


class PolishedRegistryTab(_BasePolishedRegistryTab):
    """Ensures lazy path restoration visibly expands every resolved parent."""

    def _continue_tree_navigation(self, expanded_item: str) -> None:
        nav: dict[str, Any] | None = self._tree_navigation
        if not nav or not self._navigation_in_progress:
            return
        if expanded_item != nav.get("current_item"):
            return

        # This node has just been loaded remotely. Open it now, after loading,
        # so its children are visible without triggering duplicate lazy loads.
        try:
            self.registry_tree.item(expanded_item, open=True)
        except Exception:
            pass

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
            self._navigation_in_progress = False
            self._tree_navigation = None
            self.active_scope = {"hive": str(nav["hive"]), "path": str(nav["path"])}
            self.hive_menu.set(str(nav["hive"]))
            self._show_address(str(nav["hive"]), str(nav["path"]))
            super(_BasePolishedRegistryTab, self).refresh_current_key()
            self._remember_state()
            return

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
