import asyncio
import json
import logging

import websockets

from app.config import ClientConfig
from app.identity_manager import ClientIdentityManager
from websockets.exceptions import ConnectionClosed
from app.terminal_executor import TerminalExecutor
from app.appsettings_reader import AppSettingsReader


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
        self.terminal_executor = TerminalExecutor()
        self.appsettings_reader = AppSettingsReader()
        
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
            
            await self._send_appsettings(websocket)
            
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

            elif message_type == "terminal_autocomplete":
                await self._handle_terminal_autocomplete(websocket, payload)
            
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
        Εκτελεί πραγματική CMD/PowerShell εντολή και επιστρέφει αποτέλεσμα.
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

        execution_result = await self.terminal_executor.execute_command(
            shell=shell,
            command=command
        )

        result_message = {
            "type": "terminal_result",
            "command_id": command_id,
            "client_code": self.identity["client_code"],
            **execution_result
        }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_terminal_autocomplete(self, websocket, payload: dict) -> None:
        """
        Υπολογίζει autocomplete προτάσεις για το Remote Terminal.
        """

        request_id = payload.get("request_id", "")
        shell = payload.get("shell", "cmd")
        command_text = payload.get("command_text", "")

        autocomplete_result = self.terminal_executor.get_autocomplete_matches(
            shell=shell,
            command_text=command_text
        )

        result_message = {
            "type": "terminal_autocomplete_result",
            "request_id": request_id,
            "client_code": self.identity["client_code"],
            **autocomplete_result
        }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _send_appsettings(self, websocket) -> None:
        """
        Διαβάζει αυτόματα το appsettings.production.json και το στέλνει στον server.
        """

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()

            message = {
                "type": "appsettings_result",
                "client_code": self.identity["client_code"],
                **appsettings_data
            }

            await websocket.send(json.dumps(message, ensure_ascii=False))

            logger.info(
                "Στάλθηκαν appsettings στον server. file_found=%s",
                appsettings_data.get("file_found")
            )

        except Exception as exc:
            logger.exception("Αποτυχία ανάγνωσης appsettings.production.json.")

            message = {
                "type": "appsettings_result",
                "client_code": self.identity["client_code"],
                "file_found": False,
                "file_path": None,
                "raw_json": None,
                "raw_text": None,
                "database_connection": None,
                "database_server": None,
                "database_name": None,
                "database_user": None,
                "database_password": None,
                "last_read_at": None,
                "error": str(exc)
            }

            await websocket.send(json.dumps(message, ensure_ascii=False))