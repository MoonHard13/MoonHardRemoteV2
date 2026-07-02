import asyncio
import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import websockets


logger = logging.getLogger(__name__)


class DashboardWebSocketClient:
    """
    WebSocket client που συνδέει το dashboard με τον Render server.

    Όλες οι αποστολές/λήψεις γίνονται στο ίδιο asyncio loop ώστε να αποφεύγονται
    race conditions από πολλά διαφορετικά threads που χρησιμοποιούν το ίδιο websocket.
    """

    def __init__(
        self,
        websocket_url: str,
        dashboard_token: str,
        on_message_callback: Callable[[dict[str, Any]], None],
        on_status_callback: Callable[[str], None]
    ) -> None:
        """
        Αρχικοποιεί τον WebSocket client του dashboard.
        """

        self.websocket_url = websocket_url
        self.dashboard_token = dashboard_token
        self.on_message_callback = on_message_callback
        self.on_status_callback = on_status_callback

        self.websocket = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_queue: asyncio.Queue[dict[str, Any] | None] | None = None

    def start(self) -> None:
        """
        Ξεκινάει το WebSocket σε ξεχωριστό thread ώστε να μην παγώνει το GUI.
        """

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """
        Ζητάει τερματισμό της WebSocket σύνδεσης.
        """

        self._stop_event.set()

        loop = self._loop
        send_queue = self._send_queue
        websocket = self.websocket

        if loop and loop.is_running():
            if send_queue:
                loop.call_soon_threadsafe(send_queue.put_nowait, None)

            if websocket:
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(websocket.close())
                )

    def _run_async_loop(self) -> None:
        """
        Δημιουργεί νέο asyncio loop για το thread του WebSocket.
        """

        asyncio.run(self._connect_forever())

    async def _connect_forever(self) -> None:
        """
        Συνδέεται συνεχώς στο WebSocket και κάνει reconnect αν χαθεί η σύνδεση.
        """

        self._loop = asyncio.get_running_loop()
        self._send_queue = asyncio.Queue()

        while not self._stop_event.is_set():
            try:
                self.on_status_callback("Σύνδεση...")

                async with websockets.connect(self.websocket_url) as websocket:
                    self.websocket = websocket

                    logger.info("Dashboard WebSocket connected.")

                    auth_message = {
                        "type": "authenticate",
                        "token": self.dashboard_token
                    }

                    await websocket.send(json.dumps(auth_message, ensure_ascii=False))

                    self.on_status_callback("Online")

                    receive_task = asyncio.create_task(self._receive_loop(websocket))
                    send_task = asyncio.create_task(self._send_loop(websocket))

                    done_tasks, pending_tasks = await asyncio.wait(
                        {receive_task, send_task},
                        return_when=asyncio.FIRST_EXCEPTION
                    )

                    for task in pending_tasks:
                        task.cancel()

                    for task in done_tasks:
                        task.result()

            except Exception:
                if not self._stop_event.is_set():
                    logger.exception("Dashboard WebSocket connection failed.")
                    self.on_status_callback("Offline - επανασύνδεση...")

            finally:
                self.websocket = None

            if not self._stop_event.is_set():
                await asyncio.sleep(5)

    async def _receive_loop(self, websocket) -> None:
        """
        Διαβάζει μηνύματα από τον server.
        """

        while not self._stop_event.is_set():
            message = await websocket.recv()
            payload = json.loads(message)
            message_type = payload.get("type", "unknown")

            logger.info("Dashboard received message type: %s", message_type)
            self.on_message_callback(payload)

    async def _send_loop(self, websocket) -> None:
        """
        Στέλνει μηνύματα στον server από ένα ασφαλές asyncio queue.
        """

        if not self._send_queue:
            return

        while not self._stop_event.is_set():
            message = await self._send_queue.get()

            if message is None:
                return

            await websocket.send(json.dumps(message, ensure_ascii=False))

    def send_message(self, message: dict[str, Any]) -> None:
        """
        Βάζει μήνυμα στην ουρά αποστολής από το GUI thread.
        """

        loop = self._loop
        send_queue = self._send_queue

        if not loop or not loop.is_running() or not send_queue or not self.websocket:
            logger.warning("Cannot send message. Dashboard WebSocket is not connected.")
            return

        loop.call_soon_threadsafe(send_queue.put_nowait, message)