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
from app.windows_services import WindowsServicesReader
from app.process_reader import ProcessReader
from app.client_update import ClientUpdateChecker


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
        self.windows_services_reader = WindowsServicesReader()
        self.process_reader = ProcessReader()
        self.client_update_checker = ClientUpdateChecker(self.config)
        
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

            elif message_type == "provider_get_note_types":
                await self._handle_provider_get_note_types(websocket, payload)
                
            elif message_type == "provider_delete_payway":
                await self._handle_provider_delete_payway(websocket, payload)
                
            elif message_type == "provider_delete_mydata":
                await self._handle_provider_delete_mydata(websocket, payload)

            elif message_type == "services_get":
                await self._handle_services_get(websocket, payload)

            elif message_type == "service_restart":
                await self._handle_service_restart(websocket, payload)
                
            elif message_type == "service_start":
                await self._handle_service_start(websocket, payload)

            elif message_type == "service_stop":
                await self._handle_service_stop(websocket, payload)

            elif message_type == "processes_get":
                await self._handle_processes_get(websocket, payload)

            elif message_type == "process_kill":
                await self._handle_process_kill(websocket, payload)

            elif message_type == "client_update_check":
                await self._handle_client_update_check(websocket, payload)

            elif message_type == "client_update_download":
                await self._handle_client_update_download(websocket, payload)

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

    async def _handle_provider_delete_mydata(self, websocket, payload: dict) -> None:
        """
        Διαγράφει MyDATA responses για επιλεγμένα παραστατικά από τον client υπολογιστή.
        Δεν αποθηκεύει αποτελέσματα στον server.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        documents = payload.get("documents") or []

        logger.info(
            "Λήφθηκε Provider delete MyDATA request. request_id=%s bo_connection_id=%s invoices=%s",
            request_id,
            bo_connection_id,
            len(documents)
        )

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            bo_connections = appsettings_data.get("bo_connections") or []

            selected_connection = self._get_bo_connection_by_id(
                bo_connections=bo_connections,
                bo_connection_id=bo_connection_id
            )

            if not selected_connection:
                raise RuntimeError(
                    f"BOConnection ID {bo_connection_id} was not found."
                )

            database_connection = selected_connection.get("DatabaseConnection")

            if not database_connection:
                raise RuntimeError(
                    f"BOConnection ID {bo_connection_id} has no DatabaseConnection."
                )

            delete_result = await asyncio.to_thread(
                self.provider_service.delete_mydata_for_documents,
                database_connection,
                documents,
                30
            )

            result_message = {
                "type": "provider_delete_mydata_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **delete_result
            }

        except Exception as exc:
            logger.exception("Provider delete MyDATA request failed.")

            result_message = {
                "type": "provider_delete_mydata_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "documents": documents,
                "deleted_success_rows": 0,
                "deleted_response_rows": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_processes_get(self, websocket, payload: dict) -> None:
        """
        Διαβάζει running processes από τον client και επιστρέφει αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")

        try:
            processes_result = await asyncio.to_thread(
                self.process_reader.get_processes
            )

            result_message = {
                "type": "processes_get_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **processes_result
            }

        except Exception as exc:
            logger.exception("Process list read failed.")

            result_message = {
                "type": "processes_get_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "error": str(exc),
                "processes": [],
                "count": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_process_kill(self, websocket, payload: dict) -> None:
        """
        Τερματίζει process στον client και επιστρέφει αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")
        pid = payload.get("pid", "")
        process_name = payload.get("process_name", "")

        try:
            kill_result = await asyncio.to_thread(
                self.process_reader.kill_process,
                int(pid),
                process_name
            )

            result_message = {
                "type": "process_kill_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **kill_result
            }

        except Exception as exc:
            logger.exception("Process kill failed.")

            result_message = {
                "type": "process_kill_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "pid": pid,
                "process_name": process_name,
                "error": str(exc)
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

    async def _handle_client_update_check(self, websocket, payload: dict) -> None:
        """
        Ελέγχει αν υπάρχει διαθέσιμη νεότερη έκδοση client.
        """

        request_id = payload.get("request_id", "")

        try:
            update_result = await asyncio.to_thread(
                self.client_update_checker.check_for_update
            )

            result_message = {
                "type": "client_update_check_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **update_result
            }

        except Exception as exc:
            logger.exception("Client update check failed.")

            result_message = {
                "type": "client_update_check_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "current_version": self.config.app_version,
                "latest_version": "",
                "update_available": False,
                "download_url": "",
                "sha256": "",
                "mandatory": False,
                "release_notes": "",
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
    
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

    async def _handle_services_get(self, websocket, payload: dict) -> None:
        """
        Διαβάζει Windows services από τον client και επιστρέφει το αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")

        try:
            services_result = await asyncio.to_thread(
                self.windows_services_reader.get_services
            )

            result_message = {
                "type": "services_get_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **services_result
            }

        except Exception as exc:
            logger.exception("Windows services read failed.")

            result_message = {
                "type": "services_get_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "error": str(exc),
                "services": [],
                "count": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_service_restart(self, websocket, payload: dict) -> None:
        """
        Κάνει restart Windows service στον client και επιστρέφει αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")
        service_name = payload.get("service_name", "")

        try:
            restart_result = await asyncio.to_thread(
                self.windows_services_reader.restart_service,
                service_name
            )

            result_message = {
                "type": "service_restart_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **restart_result
            }

        except Exception as exc:
            logger.exception("Windows service restart failed.")

            result_message = {
                "type": "service_restart_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "service_name": service_name,
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_service_start(self, websocket, payload: dict) -> None:
        """
        Ξεκινάει Windows service στον client και επιστρέφει αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")
        service_name = payload.get("service_name", "")

        try:
            start_result = await asyncio.to_thread(
                self.windows_services_reader.start_service,
                service_name
            )

            result_message = {
                "type": "service_start_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **start_result
            }

        except Exception as exc:
            logger.exception("Windows service start failed.")

            result_message = {
                "type": "service_start_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "service_name": service_name,
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))


    async def _handle_service_stop(self, websocket, payload: dict) -> None:
        """
        Σταματάει Windows service στον client και επιστρέφει αποτέλεσμα στο dashboard.
        """

        request_id = payload.get("request_id", "")
        service_name = payload.get("service_name", "")

        try:
            stop_result = await asyncio.to_thread(
                self.windows_services_reader.stop_service,
                service_name
            )

            result_message = {
                "type": "service_stop_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **stop_result
            }

        except Exception as exc:
            logger.exception("Windows service stop failed.")

            result_message = {
                "type": "service_stop_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "service_name": service_name,
                "error": str(exc)
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
        
    async def _handle_provider_get_note_types(self, websocket, payload: dict) -> None:
        """
        Φέρνει Note Types για Delete MyDATA από τον client υπολογιστή.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))

        logger.info(
            "Λήφθηκε Provider note types request. request_id=%s bo_connection_id=%s",
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

            note_types_result = await asyncio.to_thread(
                self.provider_service.fetch_note_types,
                database_connection,
                30
            )

            result_message = {
                "type": "provider_get_note_types_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **note_types_result
            }

        except Exception as exc:
            logger.exception("Provider note types request failed.")

            result_message = {
                "type": "provider_get_note_types_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "error": str(exc),
                "note_types": [],
                "count": 0
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_client_update_check(self, websocket, payload: dict) -> None:
        """
        Ελέγχει αν υπάρχει διαθέσιμη νεότερη έκδοση client.
        """

        request_id = payload.get("request_id", "")

        try:
            update_result = await asyncio.to_thread(
                self.client_update_checker.check_for_update
            )

            result_message = {
                "type": "client_update_check_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **update_result
            }

        except Exception as exc:
            logger.exception("Client update check failed.")

            result_message = {
                "type": "client_update_check_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "current_version": self.config.app_version,
                "latest_version": "",
                "update_available": False,
                "download_url": "",
                "sha256": "",
                "mandatory": False,
                "release_notes": "",
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_client_update_download(self, websocket, payload: dict) -> None:
        """
        Κατεβάζει update package από GitHub Releases και επιστρέφει αποτέλεσμα.
        """

        request_id = payload.get("request_id", "")
        download_url = payload.get("download_url", "")
        expected_sha256 = payload.get("sha256", "")
        latest_version = payload.get("latest_version", "")

        try:
            download_result = await asyncio.to_thread(
                self.client_update_checker.download_update_package,
                download_url,
                expected_sha256,
                latest_version
            )

            result_message = {
                "type": "client_update_download_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **download_result
            }

        except Exception as exc:
            logger.exception("Client update download failed.")

            result_message = {
                "type": "client_update_download_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "download_url": download_url,
                "saved_path": "",
                "file_size_bytes": 0,
                "expected_sha256": expected_sha256,
                "actual_sha256": "",
                "sha256_verified": False,
                "latest_version": latest_version,
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))