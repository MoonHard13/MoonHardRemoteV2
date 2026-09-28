"""Read-only Registry capture support used by Registry Compare."""

from __future__ import annotations

import time
from typing import Any, Callable

from app.registry_service_safe import SafeRegistryService


class RegistryCompareService(SafeRegistryService):
    """Extends the safe Registry service with a non-persistent scoped capture."""

    def execute(
        self,
        operation: str,
        parameters: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if operation != "capture_scope":
            return super().execute(operation, parameters, progress_callback)

        started = time.perf_counter()
        try:
            result = self.capture_scope(**(parameters or {}))
            return {
                "operation": operation,
                "success": True,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                **result,
            }
        except Exception as exc:
            return {
                "operation": operation,
                "success": False,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error": self._safe_error(exc),
            }

    def capture_scope(
        self,
        hive: str,
        path: str = "",
        view: str = "default",
        max_entries: int = 5000,
    ) -> dict[str, Any]:
        """Capture Registry data for compare without writing a snapshot to disk."""

        limit = self._bounded_int(
            max_entries,
            1,
            self.MAX_SNAPSHOT_ENTRIES,
            "max_entries",
        )
        tree, count, truncated = self._capture_tree(hive, path, view, limit)
        return {
            "hive": self._normalize_hive(hive),
            "path": self._normalize_path(path),
            "view": self._normalize_view(view),
            "entry_count": count,
            "truncated": truncated,
            "tree": tree,
        }
