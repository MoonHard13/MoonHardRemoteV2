import asyncio
import json
import logging

import websockets

from app.config import ClientConfig
from app.identity_manager import ClientIdentityManager
from websockets.exceptions import ConnectionClosed
from app.terminal_executor import TerminalExecutor
from app.appsettings_reader import AppSettingsReader
from app.sql_executor import SqlExecutor
from app.provider.provider_service import ProviderService


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
        self.sql_executor = SqlExecutor()
        self.provider_service = ProviderService()
        
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
                
            elif message_type == "sql_execute":
                await self._handle_sql_execute(websocket, payload)

            elif message_type == "sql_test_connection":
                await self._handle_sql_test_connection(websocket, payload)

            elif message_type == "sql_cancel":
                await self._handle_sql_cancel(websocket, payload)
                
            elif message_type == "provider_search_invoices":
                await self._handle_provider_search_invoices(websocket, payload)

            elif message_type == "provider_send_invoices":
                await self._handle_provider_send_invoices(websocket, payload)

            elif message_type == "provider_get_errors":
                await self._handle_provider_get_errors(websocket, payload)
                
            elif message_type == "provider_get_payways":
                await self._handle_provider_get_payways(websocket, payload)
                
            elif message_type == "provider_delete_payway":
                await self._handle_provider_delete_payway(websocket, payload)

    async def _handle_provider_get_payways(self, websocket, payload: dict) -> None:
        """
        Φέρνει τρόπους πληρωμής για παραστατικό από τον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        invoice_id = payload.get("invoice_id", "")

        logger.info(
            "Λήφθηκε Provider payways request. request_id=%s bo_connection_id=%s invoice_id=%s",
            request_id,
            bo_connection_id,
            invoice_id
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            payways_result = await asyncio.to_thread(
                self.provider_service.get_invoice_payways,
                database_connection,
                invoice_id,
                30
            )

            result_message = {
                "type": "provider_get_payways_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "invoice_id": invoice_id,
                **payways_result
            }

        except Exception as exc:
            logger.exception("Provider payways request failed.")

            result_message = {
                "type": "provider_get_payways_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "invoice_id": invoice_id,
                "success": False,
                "error": str(exc),
                "payways": [],
                "count": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
            
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
            
    async def _handle_sql_execute(self, websocket, payload: dict) -> None:
        """
        Εκτελεί SQL query χρησιμοποιώντας BOConnection ID από appsettings.production.json.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        sql_text = payload.get("sql_text", "")
        timeout = int(payload.get("timeout", 60))

        logger.info(
            "Λήφθηκε SQL execute request. request_id=%s bo_connection_id=%s",
            request_id,
            bo_connection_id
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            execution_result = await asyncio.to_thread(
                self.sql_executor.execute_sql,
                request_id,
                database_connection,
                sql_text,
                timeout
            )

            result_message = {
                "type": "sql_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "driver": execution_result.get("driver"),
                "elapsed_ms": execution_result.get("elapsed_ms"),
                "success": execution_result.get("success"),
                "error": execution_result.get("error"),
                "batches": execution_result.get("batches", [])
            }

        except Exception as exc:
            logger.exception("SQL execution request failed.")

            result_message = {
                "type": "sql_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "driver": None,
                "elapsed_ms": None,
                "success": False,
                "error": str(exc),
                "batches": []
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    def _get_bo_connection_by_id(
        self,
        bo_connections: list[dict],
        bo_connection_id: int
    ) -> dict | None:
        """
        Βρίσκει BOConnection με βάση το ID.
        """

        for connection in bo_connections:
            if int(connection.get("ID", -1)) == bo_connection_id:
                return connection

        return None
    
    async def _handle_sql_test_connection(self, websocket, payload: dict) -> None:
        """
        Δοκιμάζει SQL σύνδεση για BOConnection ID.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        timeout = int(payload.get("timeout", 15))

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            test_result = await asyncio.to_thread(
                self.sql_executor.test_connection,
                database_connection,
                timeout
            )

            result_message = {
                "type": "sql_test_connection_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **test_result
            }

        except Exception as exc:
            logger.exception("SQL test connection request failed.")

            result_message = {
                "type": "sql_test_connection_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "driver": None,
                "elapsed_ms": None
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_sql_cancel(self, websocket, payload: dict) -> None:
        """
        Ακυρώνει ενεργό SQL query.
        """

        request_id = payload.get("request_id", "")

        cancel_result = self.sql_executor.cancel_sql(request_id)

        result_message = {
            "type": "sql_cancel_result",
            "request_id": request_id,
            "client_code": self.identity["client_code"],
            **cancel_result
        }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_provider_search_invoices(self, websocket, payload: dict) -> None:
        """
        Εκτελεί remote MUPT invoice search στον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        start_date = payload.get("start_date", "")
        end_date = payload.get("end_date", "")
        afm = payload.get("afm", "")
        invoice_type = payload.get("invoice_type", "")

        logger.info(
            "Λήφθηκε Provider invoice search. request_id=%s bo_connection_id=%s",
            request_id,
            bo_connection_id
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            search_result = await asyncio.to_thread(
                self.provider_service.search_invoices,
                database_connection,
                start_date,
                end_date,
                afm,
                invoice_type,
                30
            )

            result_message = {
                "type": "provider_search_invoices_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **search_result
            }

        except Exception as exc:
            logger.exception("Provider invoice search failed.")

            result_message = {
                "type": "provider_search_invoices_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "invoices": [],
                "count": 0,
                "table": None
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_provider_send_invoices(self, websocket, payload: dict) -> None:
        """
        Στέλνει παραστατικά μέσω Provider API από τον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        api_url = payload.get("api_url", "")
        invoice_ids = payload.get("invoice_ids") or []
        timeout = int(payload.get("timeout", 60))
        max_workers = int(payload.get("max_workers", 6))

        logger.info(
            "Λήφθηκε Provider send request. request_id=%s bo_connection_id=%s invoices=%s",
            request_id,
            bo_connection_id,
            len(invoice_ids)
        )

        try:
            send_result = await asyncio.to_thread(
                self.provider_service.send_invoices,
                api_url,
                invoice_ids,
                timeout,
                max_workers
            )

            result_message = {
                "type": "provider_send_invoices_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **send_result
            }

        except Exception as exc:
            logger.exception("Provider send request failed.")

            result_message = {
                "type": "provider_send_invoices_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "elapsed_ms": None,
                "results": []
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_provider_get_errors(self, websocket, payload: dict) -> None:
        """
        Φέρνει Provider/MyDATA errors από τον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        start_date = payload.get("start_date", "")
        end_date = payload.get("end_date", "")
        limit = int(payload.get("limit", 300))

        logger.info(
            "Λήφθηκε Provider errors request. request_id=%s bo_connection_id=%s",
            request_id,
            bo_connection_id
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            errors_result = await asyncio.to_thread(
                self.provider_service.get_mydata_errors,
                database_connection,
                start_date,
                end_date,
                limit,
                30
            )

            result_message = {
                "type": "provider_get_errors_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **errors_result
            }

        except Exception as exc:
            logger.exception("Provider errors request failed.")

            result_message = {
                "type": "provider_get_errors_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "errors": [],
                "count": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_provider_delete_payway(self, websocket, payload: dict) -> None:
        """
        Διαγράφει τρόπο πληρωμής από τον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        invoice_id = payload.get("invoice_id", "")
        sales_payway_oid = payload.get("sales_payway_oid", "")

        logger.info(
            "Λήφθηκε Provider delete payway request. request_id=%s bo_connection_id=%s invoice_id=%s sales_payway_oid=%s",
            request_id,
            bo_connection_id,
            invoice_id,
            sales_payway_oid
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} has no DatabaseConnection.")

            delete_result = await asyncio.to_thread(
                self.provider_service.delete_payway,
                database_connection,
                sales_payway_oid,
                30
            )

            result_message = {
                "type": "provider_delete_payway_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "invoice_id": invoice_id,
                **delete_result
            }

        except Exception as exc:
            logger.exception("Provider delete payway request failed.")

            result_message = {
                "type": "provider_delete_payway_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "invoice_id": invoice_id,
                "sales_payway_oid": sales_payway_oid,
                "success": False,
                "error": str(exc),
                "deleted_main_rows": 0,
                "deleted_history_rows": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))