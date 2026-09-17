import logging
from collections import deque
from threading import RLock

from app.provider_diagnostic.models import APIDiagnostic


logger = logging.getLogger(__name__)


class APIDiagnosticStore:
    """Κρατά περιορισμένο ιστορικό πραγματικών API attempts μόνο στη RAM."""

    def __init__(self, limit: int = 1000) -> None:
        self._entries: deque[APIDiagnostic] = deque(maxlen=limit)
        self._lock = RLock()
        self._closed = False

    def add(self, entry: APIDiagnostic) -> None:
        with self._lock:
            if self._closed:
                return
            self._entries.append(entry)
        logger.info("Κλήση Provider. operation=%s duration_ms=%s status=%s count=%s category=%s",
                    entry.operation, entry.duration_ms, entry.http_status,
                    entry.records, entry.error_category or "success")

    def entries(self, outcome: str = "All", endpoint: str = "", status: str = "") -> list[APIDiagnostic]:
        with self._lock:
            entries = list(self._entries)
        return [entry for entry in entries
                if (outcome == "All" or entry.success == (outcome == "Success"))
                and endpoint.lower() in entry.endpoint.lower()
                and (not status or str(entry.http_status) == status)]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._entries.clear()
