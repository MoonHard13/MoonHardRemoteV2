import asyncio
import json
import logging

import websockets

from app.config import ClientConfig
from app.identity_manager import ClientIdentityManager
from websockets.exceptions import ConnectionClosed


logger = logging.getLogger(__name__)


class MoonHardClientAgent:
    """
    Κεντρικός client agent που συνδέεται αυτόματα στον Render server.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί ρυθμίσεις και ταυτότητα client.
        """

        self.config = ClientConfig()
        self.identity_manager = ClientIdentityManager(self.config.identity_file)
        self.identity = self.identity_manager.load_or_create_identity()

    async def run_forever(self) -> None:
        """
        Κρατάει τον client ενεργό και κάνει reconnect αν χαθεί η σύνδεση.
        """

        while True:
            try:
                await self._connect_once()

            except ConnectionClosed as exc:
                logger.warning(
                    "Η WebSocket σύνδεση έκλεισε (%s). Νέα προσπάθεια σε %s δευτερόλεπτα.",
                    exc,
                    self.config.reconnect_seconds
                )

                await asyncio.sleep(self.config.reconnect_seconds)

            except Exception:
                logger.exception(
                    "Η σύνδεση απέτυχε απρόσμενα. Νέα προσπάθεια σε %s δευτερόλεπτα.",
                    self.config.reconnect_seconds
                )

                await asyncio.sleep(self.config.reconnect_seconds)

    async def _connect_once(self) -> None:
        """
        Εκτελεί μία WebSocket σύνδεση προς τον server.
        Αν η σύνδεση κλείσει, η run_forever θα κάνει reconnect.
        """

        logger.info("Σύνδεση στο WebSocket: %s", self.config.server_websocket_url)

        async with websockets.connect(self.config.server_websocket_url) as websocket:
            logger.info("WebSocket σύνδεση επιτυχής.")

            register_message = self._create_register_message()

            await websocket.send(json.dumps(register_message, ensure_ascii=False))
            logger.info("Στάλθηκε register message για client_code=%s", self.identity["client_code"])

            response = await websocket.recv()
            logger.info("Απάντηση server: %s", response)

            await asyncio.gather(
                self._listen_forever(websocket),
                self._send_heartbeat_forever(websocket)
            )

    def _create_register_message(self) -> dict:
        """
        Δημιουργεί το register μήνυμα που στέλνει ο client στον server.
        """

        return {
            "type": "register",
            "token": self.config.client_token,
            "client_code": self.identity["client_code"],
            "display_name": self.identity.get("display_name"),
            "pc_name": self.identity.get("pc_name"),
            "username": self.identity.get("username"),
            "app_version": self.config.app_version,
        }

    async def _listen_forever(self, websocket) -> None:
        """
        Κρατάει τη σύνδεση ενεργή και ακούει μελλοντικά μηνύματα από τον server.
        """

        while True:
            message = await websocket.recv()
            logger.info("Μήνυμα από server: %s", message)

            payload = json.loads(message)
            message_type = payload.get("type")

            if message_type == "terminal_command":
                await self._handle_terminal_command(websocket, payload)
            
    async def _send_heartbeat_forever(self, websocket) -> None:
        """
        Στέλνει περιοδικό heartbeat στον server για να ενημερώνεται το last_seen.
        """

        while True:
            await asyncio.sleep(self.config.heartbeat_seconds)

            heartbeat_message = {
                "type": "heartbeat",
                "client_code": self.identity["client_code"]
            }

            await websocket.send(json.dumps(heartbeat_message, ensure_ascii=False))

            logger.info(
                "Στάλθηκε heartbeat για client_code=%s",
                self.identity["client_code"]
            )

    async def _handle_terminal_command(self, websocket, payload: dict) -> None:
        """
        Προσωρινός handler για terminal commands.
        Προς το παρόν δεν εκτελεί πραγματική εντολή, απλώς επιβεβαιώνει routing.
        """

        command_id = payload.get("command_id", "")
        shell = payload.get("shell", "cmd")
        command = payload.get("command", "")

        logger.info(
            "Λήφθηκε terminal command. command_id=%s shell=%s command=%s",
            command_id,
            shell,
            command
        )

        result_message = {
            "type": "terminal_result",
            "command_id": command_id,
            "client_code": self.identity["client_code"],
            "shell": shell,
            "command": command,
            "stdout": f"Routing OK. Client received command: {command}",
            "stderr": "",
            "exit_code": 0,
            "current_directory": ""
        }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))