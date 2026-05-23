import asyncio
import json
import logging
import threading
from collections.abc import Callable
from typing import Any
from websockets.asyncio.client import ClientConnection

import websockets


logger = logging.getLogger(__name__)


class DashboardWebSocketClient:
    """
    WebSocket client που συνδέει το dashboard με τον Render server.
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

    def _run_async_loop(self) -> None:
        """
        Δημιουργεί νέο asyncio loop για το thread του WebSocket.
        """

        asyncio.run(self._connect_forever())

    async def _connect_forever(self) -> None:
        """
        Συνδέεται συνεχώς στο WebSocket και κάνει reconnect αν χαθεί η σύνδεση.
        """

        while not self._stop_event.is_set():
            try:
                self.on_status_callback("Σύνδεση...")

                
                async with websockets.connect(self.websocket_url) as websocket:
                    logger.info("Dashboard WebSocket connected.")

                    auth_message = {
                        "type": "authenticate",
                        "token": self.dashboard_token
                    }

                    await websocket.send(json.dumps(auth_message, ensure_ascii=False))

                    self.on_status_callback("Online")

                    while not self._stop_event.is_set():
                        message = await websocket.recv()
                        payload = json.loads(message)

                        logger.info("Dashboard received message: %s", payload)
                        self.on_message_callback(payload)

                self.websocket = websocket

            except Exception:
                logger.exception("Dashboard WebSocket connection failed.")
                self.on_status_callback("Offline - επανασύνδεση...")

                self.websocket = None

                await asyncio.sleep(5)

    async def _send_json_safe(self, message: dict[str, Any]) -> None:
        """
        Placeholder για μελλοντική αποστολή μηνυμάτων.
        Προς το παρόν δεν χρησιμοποιείται επειδή το websocket είναι τοπική μεταβλητή.
        """
        
    def send_message(self, message: dict[str, Any]) -> None:
        """
        Στέλνει μήνυμα στον server από το GUI thread.
        """

        if not self.websocket:
            logger.warning("Cannot send message. Dashboard WebSocket is not connected.")
            return

        threading.Thread(
            target=self._send_message_thread,
            args=(message,),
            daemon=True
        ).start()

    def _send_message_thread(self, message: dict[str, Any]) -> None:
        """
        Στέλνει μήνυμα σε ξεχωριστό thread ώστε να μην παγώνει το GUI.
        """

        asyncio.run(self._send_message_async(message))

    async def _send_message_async(self, message: dict[str, Any]) -> None:
        """
        Ασύγχρονη αποστολή JSON μηνύματος στον WebSocket server.
        """

        if not self.websocket:
            return

        await self.websocket.send(json.dumps(message, ensure_ascii=False))