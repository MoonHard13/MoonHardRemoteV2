from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, Thread

from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError


class BackgroundTask:
    """Εκτελεί μία εργασία χωρίς προσπέλαση Tk από worker thread."""

    def __init__(self) -> None:
        self.cancel_event = Event()
        self._queue: Queue = Queue(maxsize=1)
        self._progress: Queue = Queue(maxsize=1)
        self._thread: Thread | None = None
        self._closed = False

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, operation: Callable[[Event], object]) -> bool:
        if self.busy or self._closed:
            return False
        self.cancel_event.clear()
        self.poll_progress()

        def worker() -> None:
            try:
                value = operation(self.cancel_event)
                error = None
            except ProviderAPIError as exc:
                value, error = None, exc
            except Exception:
                # Δεν μεταφέρουμε πιθανώς ευαίσθητα exception strings στο GUI.
                value, error = None, ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE)
            if self.cancel_event.is_set():
                value, error = None, ProviderAPIError(ErrorCategory.CANCELLED)
            if not self._closed:
                self._queue.put((value, error))

        self._thread = Thread(target=worker, daemon=True, name="ProviderDiagnostic")
        self._thread.start()
        return True

    def poll(self) -> tuple | None:
        try:
            result = self._queue.get_nowait()
        except Empty:
            return None
        self._thread = None
        if self.cancel_event.is_set():
            return None, ProviderAPIError(ErrorCategory.CANCELLED)
        return result

    def cancel(self) -> None:
        self.cancel_event.set()

    def report_progress(self, value) -> None:
        if self._closed:
            return
        self.poll_progress()
        self._progress.put_nowait(value)

    def poll_progress(self):
        try:
            return self._progress.get_nowait()
        except Empty:
            return None

    def close(self) -> None:
        self._closed = True
        self.cancel()
