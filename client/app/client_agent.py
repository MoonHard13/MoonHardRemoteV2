import asyncio
import json
import logging
import subprocess
import time
import urllib.request
import winreg

import websockets

from app.config import ClientConfig
from app.backup_service import BackupCoordinator, BackupScheduler
from app.database_maintenance_service import DatabaseMaintenanceService
from app.identity_manager import ClientIdentityManager
from websockets.exceptions import ConnectionClosed
from app.terminal_executor import TerminalExecutor
from app.terminal_session import TerminalSessionManager
from app.appsettings_reader import AppSettingsReader
from app.sql_executor import SqlExecutor
from app.sql_transport import SqlResultTransport
from app.provider.provider_service import ProviderService
from app.provider.transmitted_invoices import TransmittedInvoicesService
from app.windows_services import WindowsServicesReader
from app.process_reader import ProcessReader
from app.client_update import ClientUpdateChecker
from app.senario_prosorinon_service import SenarioProsorinonService
from pathlib import Path


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
        self.terminal_sessions = TerminalSessionManager()
        self.appsettings_reader = AppSettingsReader()
        self.sql_executor = SqlExecutor()
        self.database_maintenance_service = DatabaseMaintenanceService()
        self.backup_coordinator = BackupCoordinator(
            appsettings_reader=self.appsettings_reader,
            state_file=self.config.backup_state_file,
            rclone_executable=self.config.rclone_executable,
            rclone_config_file=self.config.rclone_config_file,
        )
        self.backup_scheduler = BackupScheduler(
            self.backup_coordinator,
            interval_seconds=self.config.backup_scheduler_interval_seconds,
        )
        self.provider_service = ProviderService()
        self.transmitted_invoices_service = TransmittedInvoicesService(self.provider_service)
        self.windows_services_reader = WindowsServicesReader()
        self.process_reader = ProcessReader()
        self.client_update_checker = ClientUpdateChecker(self.config)
        self.senario_prosorinon_service = SenarioProsorinonService()
        
    async def run_forever(self) -> None:
        """
        Κρατάει τον client ενεργό και κάνει έξυπνο reconnect αν χαθεί η σύνδεση.
        """

        self.backup_scheduler.start()
        try:
            await self._run_connection_loop()
        finally:
            self.backup_scheduler.stop()

    async def _run_connection_loop(self) -> None:
        """Διατηρεί τη σύνδεση και επιτρέπει καθαρό τερματισμό του scheduler."""

        reconnect_delay = self.config.reconnect_initial_seconds

        while True:
            connection_started_at = time.monotonic()

            try:
                await self._wake_server()
                await self._connect_once()

                connected_seconds = time.monotonic() - connection_started_at

                if connected_seconds >= self.config.reconnect_reset_after_success_seconds:
                    reconnect_delay = self.config.reconnect_initial_seconds

            except ConnectionClosed as exc:
                logger.warning(
                    "Η WebSocket σύνδεση έκλεισε (%s). Νέα προσπάθεια σε %s δευτερόλεπτα.",
                    exc,
                    reconnect_delay
                )

                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * 2,
                    self.config.reconnect_max_seconds
                )

            except Exception:
                logger.exception(
                    "Η σύνδεση απέτυχε απρόσμενα. Νέα προσπάθεια σε %s δευτερόλεπτα.",
                    reconnect_delay
                )

                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(
                    reconnect_delay * 2,
                    self.config.reconnect_max_seconds
                )

    async def _wake_server(self) -> None:
        """
        Κάνει ένα μικρό HTTP wake request πριν το WebSocket reconnect.
        Χρήσιμο όταν το Render έχει κοιμηθεί ή κάνει restart.
        """

        def _request() -> None:
            request = urllib.request.Request(
                self.config.server_wake_url,
                headers={
                    "User-Agent": "MoonHardRemoteClient/1.0"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=8
            ) as response:
                response.read(128)

        try:
            await asyncio.to_thread(_request)
            logger.info("Server wake request completed: %s", self.config.server_wake_url)

        except Exception as exc:
            logger.warning("Server wake request failed: %s", exc)

    async def _connect_once(self) -> None:
        """
        Εκτελεί μία WebSocket σύνδεση προς τον server.
        Αν η σύνδεση κλείσει, η run_forever θα κάνει reconnect.
        """

        logger.info("Σύνδεση στο WebSocket: %s", self.config.server_websocket_url)

        async with websockets.connect(
            self.config.server_websocket_url,
            open_timeout=self.config.websocket_open_timeout_seconds,
            ping_interval=self.config.websocket_ping_interval_seconds,
            ping_timeout=self.config.websocket_ping_timeout_seconds
        ) as websocket:
            logger.info("WebSocket σύνδεση επιτυχής.")

            register_message = self._create_register_message()

            await websocket.send(json.dumps(register_message, ensure_ascii=False))
            logger.info("Στάλθηκε register message για client_code=%s", self.identity["client_code"])

            response = await websocket.recv()
            logger.info("Απάντηση server: %s", response)

            response_payload = json.loads(response)

            if response_payload.get("type") == "error":
                error_code = str(response_payload.get("error_code") or "")
                error_message = str(response_payload.get("message") or "Authentication failed.")

                if error_code == "TOKEN_RESET_REQUIRED":
                    self.identity_manager.rotate_client_instance_token(self.identity)

                    logger.warning(
                        "Server requested per-client token reset. Local token was rotated and client will reconnect."
                    )

                    await websocket.close()
                    return

                raise RuntimeError(error_message)

            if (
                response_payload.get("type") == "registered"
                and response_payload.get("client_token_registered")
            ):
                self.identity_manager.mark_client_token_registered(self.identity)
                logger.info("Per-client token registered/confirmed by server.")
            
            await self._send_appsettings(websocket)
            
            connection_tasks = [asyncio.create_task(self._listen_forever(websocket)),
                                asyncio.create_task(self._send_heartbeat_forever(websocket))]
            try:
                done, _ = await asyncio.wait(connection_tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in connection_tasks:
                    task.cancel()
                await asyncio.gather(*connection_tasks, return_exceptions=True)
                await self.terminal_sessions.close_all()

    def _get_installed_program_versions(self) -> dict[str, str | None]:
        """
        Διαβάζει τις εκδόσεις εγκατεστημένων Sunsoft προγραμμάτων από Windows Registry.
        """

        wanted_programs = {
            "amv_version": "AmvrosiaFull",
            "bo_version": "BackOfficeFull",
            "etp_version": "External Tax Provider",
            "aws_version": "Amvrosia Web Service",
        }

        registry_paths = [
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ),
            (
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            ),
        ]

        versions: dict[str, str | None] = {
            "amv_version": None,
            "bo_version": None,
            "etp_version": None,
            "aws_version": None,
        }

        for root_key, registry_path in registry_paths:
            try:
                with winreg.OpenKey(root_key, registry_path) as uninstall_key:
                    subkey_count = winreg.QueryInfoKey(uninstall_key)[0]

                    for index in range(subkey_count):
                        try:
                            subkey_name = winreg.EnumKey(uninstall_key, index)

                            with winreg.OpenKey(uninstall_key, subkey_name) as app_key:
                                try:
                                    display_name, _ = winreg.QueryValueEx(
                                        app_key,
                                        "DisplayName"
                                    )
                                except FileNotFoundError:
                                    continue

                                try:
                                    display_version, _ = winreg.QueryValueEx(
                                        app_key,
                                        "DisplayVersion"
                                    )
                                except FileNotFoundError:
                                    display_version = None

                                clean_display_name = str(display_name).strip().lower()

                                for version_key, wanted_name in wanted_programs.items():
                                    if clean_display_name == wanted_name.lower():
                                        versions[version_key] = (
                                            str(display_version).strip()
                                            if display_version
                                            else None
                                        )

                        except OSError:
                            continue

            except OSError:
                continue

        logger.info(
            "Installed program versions detected. AMV=%s BO=%s ETP=%s AWS=%s",
            versions.get("amv_version"),
            versions.get("bo_version"),
            versions.get("etp_version"),
            versions.get("aws_version")
        )

        return versions

    def _create_register_message(self) -> dict:
        """
        Δημιουργεί το register μήνυμα που στέλνει ο client στον server.

        Στέλνει per-client token ως κύριο token.
        Το shared CLIENT_TOKEN στέλνεται μόνο ως bootstrap_token μέχρι ο server να κάνει register
        το per-client token.
        """

        program_versions = self._get_installed_program_versions()

        client_instance_token = self.identity_manager.ensure_client_instance_token(
            self.identity
        )

        client_token_registered = bool(
            self.identity.get("client_token_registered", False)
        )

        register_message = {
            "type": "register",
            "auth_mode": "client_instance",
            "token": client_instance_token,
            "client_code": self.identity["client_code"],
            "display_name": self.identity.get("display_name"),
            "pc_name": self.identity.get("pc_name"),
            "username": self.identity.get("username"),
            "app_version": self.config.app_version,
            "amv_version": program_versions.get("amv_version"),
            "bo_version": program_versions.get("bo_version"),
            "etp_version": program_versions.get("etp_version"),
            "aws_version": program_versions.get("aws_version"),
            # Δηλώνει ρητά ποια προαιρετικά remote protocols γνωρίζει ο client.
            # Έτσι ο server δεν αφήνει νέο αίτημα να περιμένει σε παλιό client.
            "capabilities": ["database_backup_v1", "terminal_session_v1"],
        }

        if not client_token_registered:
            register_message["bootstrap_token"] = self.config.client_token

        return register_message

    async def _listen_forever(self, websocket) -> None:
        """
        Κρατάει τη σύνδεση ενεργή και ακούει μελλοντικά μηνύματα από τον server.
        """

        while True:
            message = await websocket.recv()
            payload = json.loads(message)
            if (str(payload.get("type", "")).startswith("terminal_session_")
                    or payload.get("type") == "terminal_autocomplete"):
                logger.info("Αίτημα Terminal: %s", payload.get("type"))
            elif str(payload.get("type", "")).startswith("sql_"):
                logger.info("Αίτημα SQL. type=%s request_id=%s", payload.get("type"), payload.get("request_id"))
            elif str(payload.get("type", "")).startswith("provider_transmitted_"):
                logger.info("Αίτημα διαβιβασμένων: %s", payload.get("type"))
            else:
                logger.info("Μήνυμα από server: %s", message)
            message_type = payload.get("type")

            if message_type in {"terminal_session_open", "terminal_session_command", "terminal_session_stop", "terminal_session_close"}:
                await self.terminal_sessions.handle(websocket, payload, self.identity["client_code"])

            elif message_type == "terminal_command":
                await self._handle_terminal_command(websocket, payload)

            elif message_type == "terminal_autocomplete":
                await self._handle_terminal_autocomplete(websocket, payload)
                
            elif message_type == "sql_execute":
                await self._handle_sql_execute(websocket, payload)

            elif message_type == "sql_test_connection":
                await self._handle_sql_test_connection(websocket, payload)

            elif message_type == "sql_cancel":
                await self._handle_sql_cancel(websocket, payload)

            elif message_type == "database_action":
                await self._handle_database_action(websocket, payload)

            elif message_type == "backup_request":
                await self._handle_backup_request(websocket, payload)

            elif message_type == "senario_prosorinon_run":
                await self._handle_senario_prosorinon_run(websocket, payload)
                
            elif message_type in ("provider_transmitted_search", "provider_transmitted_types"):
                await self._handle_provider_transmitted(websocket, payload)

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

            elif message_type == "client_update_extract":
                await self._handle_client_update_extract(websocket, payload)

            elif message_type == "client_update_apply":
                await self._handle_client_update_apply(websocket, payload)

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

        session = self.terminal_sessions.sessions.get(payload.get("session_id"))
        if session and shell == session.shell:
            self.terminal_executor.current_directories[shell] = Path(session.directory)
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
        Διαβάζει appsettings.production.json και στέλνει στον server μόνο safe/masked δεδομένα.
        Τα πραγματικά passwords/connection strings παραμένουν μόνο στον client.
        """

        try:
            appsettings_data = self.appsettings_reader.read_appsettings_for_server()

            message = {
                "type": "appsettings_result",
                "client_code": self.identity["client_code"],
                **appsettings_data
            }

            await websocket.send(json.dumps(message, ensure_ascii=False))

            logger.info(
                "Στάλθηκαν safe appsettings στον server. file_found=%s raw_json_sent=%s raw_text_sent=%s",
                appsettings_data.get("file_found"),
                appsettings_data.get("raw_json") is not None,
                appsettings_data.get("raw_text") is not None
            )

        except Exception as exc:
            logger.exception("Αποτυχία ανάγνωσης safe appsettings.production.json.")

            message = {
                "type": "appsettings_result",
                "client_code": self.identity["client_code"],
                "file_found": False,
                "file_path": None,
                "raw_json": None,
                "raw_text": None,
                "selected_bo_connection_id": 1,
                "bo_connections": [],
                "provider_connections": [],
                "appsettings_summary": {},
                "database_connection": None,
                "database_server": None,
                "database_name": None,
                "database_user": None,
                "database_password": None,
                "has_database_password": False,
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

        for packet in SqlResultTransport.messages(result_message):
            await websocket.send(packet)

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

    async def _handle_database_action(self, websocket, payload: dict) -> None:
        """Εκτελεί ελεγχόμενη λειτουργία συντήρησης στην επιλεγμένη βάση του client."""

        request_id = str(payload.get("request_id") or "")
        action = str(payload.get("action") or "")
        parameters = payload.get("parameters")

        try:
            bo_connection_id = int(payload.get("bo_connection_id", 1))
            timeout = int(payload.get("timeout", 60))
            appsettings_data = self.appsettings_reader.read_appsettings_production()
            selected_connection = self._get_bo_connection_by_id(
                bo_connections=appsettings_data.get("bo_connections") or [],
                bo_connection_id=bo_connection_id,
            )

            if not selected_connection:
                raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

            database_connection = selected_connection.get("DatabaseConnection")
            if not database_connection:
                raise RuntimeError(
                    f"BOConnection ID {bo_connection_id} has no DatabaseConnection."
                )

            logger.info(
                "Λήφθηκε database action. request_id=%s action=%s bo_connection_id=%s",
                request_id,
                action,
                bo_connection_id,
            )

            progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()
            event_loop = asyncio.get_running_loop()

            def report_progress(progress: dict) -> None:
                """Μεταφέρει thread-safe τα SQL progress messages στο asyncio loop."""

                event_loop.call_soon_threadsafe(
                    progress_queue.put_nowait,
                    dict(progress),
                )

            def run_action() -> dict:
                """Εκτελεί τη βάση σε worker thread και σηματοδοτεί το τέλος του stream."""

                try:
                    return self.database_maintenance_service.execute(
                        action,
                        database_connection,
                        parameters,
                        timeout,
                        report_progress,
                    )
                finally:
                    event_loop.call_soon_threadsafe(progress_queue.put_nowait, None)

            action_task = asyncio.create_task(asyncio.to_thread(run_action))

            while True:
                progress = await progress_queue.get()
                if progress is None:
                    break

                await websocket.send(
                    json.dumps(
                        {
                            "type": "database_action_progress",
                            "request_id": request_id,
                            "client_code": self.identity["client_code"],
                            "bo_connection_id": bo_connection_id,
                            "action": action,
                            **progress,
                        },
                        ensure_ascii=False,
                    )
                )

            action_result = await action_task

            result_message = {
                "type": "database_action_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **action_result,
            }

        except Exception as exc:
            logger.exception("Αποτυχία χειρισμού database action. action=%s", action)
            result_message = {
                "type": "database_action_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": payload.get("bo_connection_id", 1),
                "action": action,
                "success": False,
                "error": str(exc),
                "database_name": "",
                "driver": None,
                "elapsed_ms": None,
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_backup_request(self, websocket, payload: dict) -> None:
        """Εκτελεί backup/schedule operation τοπικά και στέλνει ασφαλή live πρόοδο."""

        request_id = str(payload.get("request_id") or "")
        operation = str(payload.get("operation") or "")
        parameters = payload.get("parameters")
        try:
            bo_connection_id = int(payload.get("bo_connection_id", 1))
            logger.info(
                "Λήφθηκε backup request. request_id=%s operation=%s bo_connection_id=%s",
                request_id,
                operation,
                bo_connection_id,
            )

            # Άμεσο acknowledgement πριν από οποιαδήποτε πρόσβαση σε SQL/path.
            # Επιτρέπει στο Dashboard να ξεχωρίζει παλιό client από πραγματικό
            # database ή permissions error.
            await websocket.send(
                json.dumps(
                    {
                        "type": "backup_progress",
                        "request_id": request_id,
                        "client_code": self.identity["client_code"],
                        "bo_connection_id": bo_connection_id,
                        "operation": operation,
                        "stage": "accepted",
                        "message": "Remote client accepted the backup request.",
                        "percent": 0,
                    },
                    ensure_ascii=False,
                )
            )

            progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()
            event_loop = asyncio.get_running_loop()

            def report_progress(progress: dict) -> None:
                """Μεταφέρει thread-safe την πρόοδο backup στο asyncio loop."""

                event_loop.call_soon_threadsafe(
                    progress_queue.put_nowait,
                    dict(progress),
                )

            def run_operation() -> dict:
                """Εκτελεί το blocking backup operation σε worker thread."""

                try:
                    return self.backup_coordinator.execute(
                        operation=operation,
                        bo_connection_id=bo_connection_id,
                        parameters=parameters,
                        progress_callback=report_progress,
                    )
                finally:
                    event_loop.call_soon_threadsafe(progress_queue.put_nowait, None)

            operation_task = asyncio.create_task(asyncio.to_thread(run_operation))
            while True:
                progress = await progress_queue.get()
                if progress is None:
                    break
                await websocket.send(
                    json.dumps(
                        {
                            "type": "backup_progress",
                            "request_id": request_id,
                            "client_code": self.identity["client_code"],
                            "bo_connection_id": bo_connection_id,
                            "operation": operation,
                            **progress,
                        },
                        ensure_ascii=False,
                    )
                )

            operation_result = await operation_task
            result_message = {
                "type": "backup_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "operation": operation,
                **operation_result,
            }
        except Exception as exc:
            logger.exception("Αποτυχία χειρισμού backup request. operation=%s", operation)
            result_message = {
                "type": "backup_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": payload.get("bo_connection_id", 1),
                "operation": operation,
                "success": False,
                "status": "failed",
                "message": "Backup operation failed.",
                "error": str(exc)[:4000],
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))

    async def _handle_senario_prosorinon_run(self, websocket, payload: dict) -> None:
        """
        Εκτελεί τους ελέγχους Σεναρίου Προσωρινών Αποδείξεων στον client.
        """

        request_id = payload.get("request_id", "")
        bo_connection_id = int(payload.get("bo_connection_id", 1))
        timeout = int(payload.get("timeout", 60))

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

            senario_result = await asyncio.to_thread(
                self.senario_prosorinon_service.run_checks,
                database_connection,
                timeout
            )

            result_message = {
                "type": "senario_prosorinon_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                **senario_result
            }

        except Exception as exc:
            logger.exception("Senario Prosorinon request failed.")

            result_message = {
                "type": "senario_prosorinon_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "bo_connection_id": bo_connection_id,
                "success": False,
                "database_name": "",
                "total": 0,
                "success_count": 0,
                "problem_count": 0,
                "results": [],
                "error": str(exc)
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
        
    async def _handle_provider_transmitted(self, websocket, payload: dict) -> None:
        """Εκτελεί ανάγνωση διαβιβασμένων αποκλειστικά στην επιλεγμένη τοπική βάση."""
        message_type = payload.get("type")
        result = TransmittedInvoicesService.failure("Μη έγκυρο BOConnection.")
        bo_id = payload.get("bo_connection_id", 1)
        try:
            if isinstance(bo_id, bool):
                raise ValueError("Μη έγκυρο BOConnection.")
            bo_id = int(bo_id)

            def execute() -> dict:
                """Διαβάζει ρυθμίσεις και SQL εκτός του βρόχου asyncio."""
                data = self.appsettings_reader.read_appsettings_production()
                selected = self._get_bo_connection_by_id(data.get("bo_connections") or [], bo_id)
                if not selected or not selected.get("DatabaseConnection"):
                    return TransmittedInvoicesService.failure("Το επιλεγμένο BOConnection δεν είναι διαθέσιμο.")
                connection_string = selected["DatabaseConnection"]
                if message_type == "provider_transmitted_types":
                    return self.transmitted_invoices_service.get_document_types(connection_string)
                return self.transmitted_invoices_service.search(connection_string, payload)

            result = await asyncio.to_thread(execute)
        except Exception as exc:
            logger.error("Αποτυχία αιτήματος διαβιβασμένων. exception_type=%s", type(exc).__name__)
        await websocket.send(json.dumps({
            **result, "type": f"{message_type}_result",
            "request_id": payload.get("request_id", ""),
            "client_code": self.identity["client_code"], "bo_connection_id": bo_id,
        }, ensure_ascii=False))

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
        
    async def _handle_client_update_extract(self, websocket, payload: dict) -> None:
        """
        Κάνει extract και validation στο downloaded update package.
        """

        request_id = payload.get("request_id", "")
        package_path = payload.get("package_path", "")
        latest_version = payload.get("latest_version", "")

        try:
            extract_result = await asyncio.to_thread(
                self.client_update_checker.extract_update_package,
                package_path,
                latest_version
            )

            result_message = {
                "type": "client_update_extract_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                **extract_result
            }

        except Exception as exc:
            logger.exception("Client update extract failed.")

            result_message = {
                "type": "client_update_extract_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "package_path": package_path,
                "extracted_path": "",
                "latest_version": latest_version,
                "extracted_files_count": 0,
                "required_items": [
                    "MoonHardRemoteClient.exe",
                    "_internal"
                ],
                "missing_items": [],
                "package_valid": False,
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
        
    async def _handle_client_update_apply(self, websocket, payload: dict) -> None:
        """
        Ξεκινάει silent external updater και επιστρέφει άμεσα αποτέλεσμα εκκίνησης.
        Ο updater θα σταματήσει το service, άρα δεν περιμένουμε να τελειώσει.
        """

        request_id = payload.get("request_id", "")
        extracted_path = payload.get("extracted_path", "")
        latest_version = payload.get("latest_version", "")

        updater_path = (
            Path(r"C:\Program Files\MoonHardRemoteV2\Client")
            / "MoonHardUpdater.exe"
        )

        try:
            if not extracted_path:
                raise ValueError("Extracted path is empty.")

            extracted_dir = Path(extracted_path)

            if not extracted_dir.exists() or not extracted_dir.is_dir():
                raise FileNotFoundError(f"Extracted path not found: {extracted_dir}")

            if not updater_path.exists() or not updater_path.is_file():
                raise FileNotFoundError(f"Updater EXE not found: {updater_path}")

            command = [
                str(updater_path),
                "--mode",
                "apply",
                "--extracted-path",
                str(extracted_dir)
            ]

            creation_flags = 0

            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creation_flags |= subprocess.CREATE_NO_WINDOW

            if hasattr(subprocess, "DETACHED_PROCESS"):
                creation_flags |= subprocess.DETACHED_PROCESS

            subprocess.Popen(
                command,
                cwd=str(updater_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                close_fds=True
            )

            logger.info(
                "Silent updater started. updater_path=%s extracted_path=%s",
                updater_path,
                extracted_dir
            )

            result_message = {
                "type": "client_update_apply_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": True,
                "extracted_path": str(extracted_dir),
                "latest_version": latest_version,
                "updater_path": str(updater_path),
                "message": "Silent updater started. Client service will restart."
            }

        except Exception as exc:
            logger.exception("Client update apply start failed.")

            result_message = {
                "type": "client_update_apply_result",
                "request_id": request_id,
                "client_code": self.identity["client_code"],
                "success": False,
                "extracted_path": extracted_path,
                "latest_version": latest_version,
                "updater_path": str(updater_path),
                "error": str(exc)
            }

        await websocket.send(json.dumps(result_message, ensure_ascii=False))
