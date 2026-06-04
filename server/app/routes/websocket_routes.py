import logging

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from app.websocket.connection_manager import connection_manager
from app.repositories.client_repository import ClientRepository

from app.config import AppConfig


router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


class WebSocketRoutes:
    """
    Routes για WebSocket επικοινωνία.
    Προς το παρόν περιέχει μόνο test dashboard WebSocket.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί τα repositories που χρειάζονται τα WebSocket routes.
        """

        self.client_repository = ClientRepository()
        self.config = AppConfig()
        self.pending_requests: dict[str, WebSocket] = {}

    def _enrich_clients_with_connection_state(self, clients: list[dict]) -> list[dict]:
        """
        Προσθέτει πραγματική WebSocket κατάσταση σύνδεσης στη λίστα clients.
        """

        for client in clients:
            client_code = str(client.get("client_code", ""))
            ws_connected = connection_manager.is_client_connected(client_code)

            client["ws_connected"] = ws_connected
            client["controllable"] = ws_connected

            if not ws_connected:
                client["status"] = "offline"

        return clients

    async def send_clients_list_to_dashboard(self, websocket: WebSocket) -> None:
        """
        Στέλνει φρέσκια λίστα clients σε συγκεκριμένο dashboard.
        """

        clients = self.client_repository.get_all_clients()
        clients = self._enrich_clients_with_connection_state(clients)

        await connection_manager.send_to_dashboard(
            websocket,
            {
                "type": "clients_list",
                "count": len(clients),
                "clients": clients
            }
        )

    async def broadcast_clients_list(self) -> None:
        """
        Στέλνει την τρέχουσα λίστα clients σε όλα τα ενεργά dashboards.
        Περιλαμβάνει και πραγματική WebSocket κατάσταση σύνδεσης.
        """

        clients = self.client_repository.get_all_clients()
        clients = self._enrich_clients_with_connection_state(clients)

        await connection_manager.broadcast_to_dashboards(
            {
                "type": "clients_list",
                "count": len(clients),
                "clients": clients
            }
        )
        
    async def client_socket(self, websocket: WebSocket) -> None:
        """
        WebSocket endpoint για client PCs.
        Ο client συνδέεται, στέλνει register μήνυμα και αποθηκεύεται στη βάση.
        """

        client_code = ""

        try:
            await websocket.accept()

            first_message = await websocket.receive_json()

            if first_message.get("token") != self.config.client_token:
                logger.warning("Client authentication failed.")
                await websocket.send_json({
                    "type": "error",
                    "message": "Authentication failed."
                })
                await websocket.close()
                return

            logger.info("Client first message received: %s", first_message)

            if first_message.get("type") != "register":
                await websocket.send_json({
                    "type": "error",
                    "message": "First message must be register."
                })
                await websocket.close()
                return

            client_code = first_message.get("client_code", "")

            if not client_code:
                await websocket.send_json({
                    "type": "error",
                    "message": "Missing client_code."
                })
                await websocket.close()
                return

            saved_client = self.client_repository.upsert_connected_client(first_message)

            await connection_manager.connect_client(client_code, websocket)

            await websocket.send_json({
                "type": "registered",
                "message": "Client registered successfully.",
                "client": saved_client
            })

            await self.broadcast_clients_list()

            while True:
                data = await websocket.receive_json()

                logger.info("Client message received from %s: %s", client_code, data)

                if data.get("type") == "heartbeat":
                    updated_client = self.client_repository.update_client_heartbeat(client_code)

                    await websocket.send_json({
                        "type": "heartbeat_ack",
                        "client_code": client_code,
                        "last_seen": updated_client.get("last_seen")
                    })

                    await self.broadcast_clients_list()
                    continue

                if data.get("type") == "appsettings_result":
                    saved_appsettings = self.client_repository.upsert_client_appsettings(data)

                    await websocket.send_json({
                        "type": "appsettings_saved",
                        "client_code": client_code,
                        "success": True,
                        "appsettings": saved_appsettings
                    })

                    await self.broadcast_clients_list()
                    continue

                if data.get("type") == "terminal_result":
                    command_id = data.get("command_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        command_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        logger.warning(
                            "No pending dashboard found for terminal result command_id=%s",
                            command_id
                        )

                    continue

                if data.get("type") == "terminal_autocomplete_result":
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        logger.warning(
                            "No pending dashboard found for autocomplete request_id=%s",
                            request_id
                        )

                    continue

                if data.get("type") in ("sql_result", "sql_test_connection_result", "sql_cancel_result"):
                    request_id = data.get("request_id", "")
                    message_type = data.get("type")

                    if message_type == "sql_cancel_result":
                        dashboard_websocket = self.pending_requests.get(request_id)
                    else:
                        dashboard_websocket = self.pending_requests.pop(
                            request_id,
                            None
                        )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("client_update_extract_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_search_invoices_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_send_invoices_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_get_errors_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_get_payways_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_get_note_types_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("process_kill_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("provider_delete_payway_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("service_restart_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("service_start_result", "service_stop_result"):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("processes_get_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("client_update_apply_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("client_update_check_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("client_update_download_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                if data.get("type") in ("services_get_result",):
                    request_id = data.get("request_id", "")

                    dashboard_websocket = self.pending_requests.pop(
                        request_id,
                        None
                    )

                    if dashboard_websocket:
                        await connection_manager.send_to_dashboard(
                            dashboard_websocket,
                            data
                        )
                    else:
                        await connection_manager.broadcast_to_dashboards(data)

                    continue

                await websocket.send_json({
                    "type": "echo",
                    "received": data
                })

        except WebSocketDisconnect:
            logger.info("Client WebSocket disconnected: %s", client_code)

            if client_code:
                connection_manager.disconnect_client(client_code)
                self.client_repository.mark_client_offline(client_code)
                await self.broadcast_clients_list()
                
        except Exception:
            logger.exception("Unexpected client WebSocket error.")

            if client_code:
                connection_manager.disconnect_client(client_code)
                self.client_repository.mark_client_offline(client_code)       
                await self.broadcast_clients_list()

    async def dashboard_socket(self, websocket: WebSocket) -> None:
        """
        WebSocket endpoint για dashboard.
        Αποδέχεται σύνδεση, ελέγχει token και στέλνει την τρέχουσα λίστα clients.
        """

        await connection_manager.connect_dashboard(websocket)

        try:
            auth_message = await websocket.receive_json()

            if (
                auth_message.get("type") != "authenticate"
                or auth_message.get("token") != self.config.dashboard_token
            ):
                logger.warning("Dashboard authentication failed.")

                await connection_manager.send_to_dashboard(
                    websocket,
                    {
                        "type": "error",
                        "message": "Authentication failed."
                    }
                )

                await websocket.close()
                return

            await connection_manager.send_to_dashboard(
                websocket,
                {
                    "type": "dashboard_connected",
                    "message": "Dashboard WebSocket connected successfully."
                }
            )

            await self.send_clients_list_to_dashboard(websocket)

            while True:
                data = await websocket.receive_json()

                logger.info("Dashboard message received: %s", data)

                if data.get("type") == "rename_client":
                    client_code = data.get("client_code", "")
                    display_name = data.get("display_name", "")

                    try:
                        renamed_client = self.client_repository.rename_client(
                            client_code=client_code,
                            display_name=display_name
                        )

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "rename_client_success",
                                "message": "Client renamed successfully.",
                                "client": renamed_client
                            }
                        )

                        await self.broadcast_clients_list()

                    except Exception as exc:
                        logger.exception("Failed to rename client.")

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "rename_client_error",
                                "message": str(exc)
                            }
                        )

                    continue

                if data.get("type") == "refresh_clients":
                    await self.send_clients_list_to_dashboard(websocket)
                    continue

                if data.get("type") == "delete_client":
                    client_code = data.get("client_code", "")

                    if not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "delete_client_error",
                                "client_code": client_code,
                                "message": "Missing client_code."
                            }
                        )
                        continue

                    try:
                        connection_manager.disconnect_client(client_code)

                        deleted_client = self.client_repository.delete_client(
                            client_code=client_code
                        )

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "delete_client_success",
                                "client_code": client_code,
                                "message": "Client deleted successfully.",
                                "deleted_client": deleted_client
                            }
                        )

                        await self.broadcast_clients_list()

                    except Exception as exc:
                        logger.exception("Failed to delete client.")

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "delete_client_error",
                                "client_code": client_code,
                                "message": str(exc)
                            }
                        )

                    continue

                if data.get("type") == "get_client_appsettings":
                    client_code = data.get("client_code", "")

                    try:
                        appsettings = self.client_repository.get_client_appsettings(
                            client_code=client_code
                        )

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_appsettings_result",
                                "client_code": client_code,
                                "success": True,
                                "appsettings": appsettings
                            }
                        )

                    except Exception as exc:
                        logger.exception("Failed to fetch client appsettings.")

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_appsettings_result",
                                "client_code": client_code,
                                "success": False,
                                "message": str(exc),
                                "appsettings": None
                            }
                        )

                    continue

                if data.get("type") == "terminal_autocomplete":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    shell = data.get("shell", "cmd")
                    command_text = data.get("command_text", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "terminal_autocomplete_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Missing request_id or client_code."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "terminal_autocomplete",
                            "request_id": request_id,
                            "client_code": client_code,
                            "shell": shell,
                            "command_text": command_text
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "terminal_autocomplete_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "client_update_extract":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    package_path = data.get("package_path", "")
                    latest_version = data.get("latest_version", "")

                    if not request_id or not client_code or not package_path:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_extract_result",
                                "request_id": request_id,
                                "client_code": client_code,
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
                                "error": "Missing request_id, client_code or package_path."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "client_update_extract",
                            "request_id": request_id,
                            "client_code": client_code,
                            "package_path": package_path,
                            "latest_version": latest_version
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_extract_result",
                                "request_id": request_id,
                                "client_code": client_code,
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
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "client_update_apply":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    extracted_path = data.get("extracted_path", "")
                    latest_version = data.get("latest_version", "")

                    if not request_id or not client_code or not extracted_path:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_apply_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "extracted_path": extracted_path,
                                "latest_version": latest_version,
                                "updater_path": "",
                                "error": "Missing request_id, client_code or extracted_path."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "client_update_apply",
                            "request_id": request_id,
                            "client_code": client_code,
                            "extracted_path": extracted_path,
                            "latest_version": latest_version
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_apply_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "extracted_path": extracted_path,
                                "latest_version": latest_version,
                                "updater_path": "",
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "terminal_command":
                    command_id = data.get("command_id", "")
                    client_code = data.get("client_code", "")
                    shell = data.get("shell", "cmd")
                    command = data.get("command", "")

                    if not command_id or not client_code or not command:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "terminal_error",
                                "command_id": command_id,
                                "client_code": client_code,
                                "message": "Missing command_id, client_code or command."
                            }
                        )
                        continue

                    self.pending_requests[command_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "terminal_command",
                            "command_id": command_id,
                            "client_code": client_code,
                            "shell": shell,
                            "command": command
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(command_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "terminal_error",
                                "command_id": command_id,
                                "client_code": client_code,
                                "message": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "sql_execute":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    bo_connection_id = data.get("bo_connection_id", 1)
                    sql_text = data.get("sql_text", "")
                    timeout = data.get("timeout", 60)

                    if not request_id or not client_code or not sql_text:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Missing request_id, client_code or sql_text."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "sql_execute",
                            "request_id": request_id,
                            "client_code": client_code,
                            "bo_connection_id": bo_connection_id,
                            "sql_text": sql_text,
                            "timeout": timeout
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Client is not connected."
                            }
                        )

                    continue



                if data.get("type") == "sql_test_connection":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Missing request_id or client_code."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "sql_cancel":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_error",
                                "request_id": request_id,
                                "client_code": client_code,
                                "message": "Missing request_id or client_code."
                            }
                        )
                        continue

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "sql_cancel_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "message": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "services_get":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "services_get_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "services": [],
                                "count": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "services_get",
                            "request_id": request_id,
                            "client_code": client_code
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "services_get_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "services": [],
                                "count": 0
                            }
                        )

                    continue

                if data.get("type") == "service_restart":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    service_name = data.get("service_name", "")

                    if not request_id or not client_code or not service_name:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "service_restart_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "service_name": service_name,
                                "error": "Missing request_id, client_code or service_name."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "service_restart",
                            "request_id": request_id,
                            "client_code": client_code,
                            "service_name": service_name
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "service_restart_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "service_name": service_name,
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") in ("service_start", "service_stop"):
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    service_name = data.get("service_name", "")
                    message_type = data.get("type")
                    result_type = f"{message_type}_result"

                    if not request_id or not client_code or not service_name:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": result_type,
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "service_name": service_name,
                                "error": "Missing request_id, client_code or service_name."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": message_type,
                            "request_id": request_id,
                            "client_code": client_code,
                            "service_name": service_name
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": result_type,
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "service_name": service_name,
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "provider_search_invoices":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_search_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "invoices": [],
                                "count": 0,
                                "table": None
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_search_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "invoices": [],
                                "count": 0,
                                "table": None
                            }
                        )

                    continue

                if data.get("type") == "provider_send_invoices":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    invoice_ids = data.get("invoice_ids") or []
                    api_url = data.get("api_url", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_send_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "total": 0,
                                "success_count": 0,
                                "fail_count": 0,
                                "elapsed_ms": None,
                                "results": []
                            }
                        )
                        continue

                    if not api_url or "invoiceid" not in api_url.lower():
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_send_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Provider API URL must contain invoiceid placeholder.",
                                "total": 0,
                                "success_count": 0,
                                "fail_count": 0,
                                "elapsed_ms": None,
                                "results": []
                            }
                        )
                        continue

                    if not invoice_ids:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_send_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "No invoice IDs selected.",
                                "total": 0,
                                "success_count": 0,
                                "fail_count": 0,
                                "elapsed_ms": None,
                                "results": []
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_send_invoices_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "total": 0,
                                "success_count": 0,
                                "fail_count": 0,
                                "elapsed_ms": None,
                                "results": []
                            }
                        )

                    continue

                if data.get("type") == "provider_get_errors":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_errors_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "errors": [],
                                "count": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_errors_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "errors": [],
                                "count": 0
                            }
                        )

                    continue

                if data.get("type") == "provider_get_payways":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    invoice_id = data.get("invoice_id", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_payways_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "payways": [],
                                "count": 0
                            }
                        )
                        continue

                    if not invoice_id:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_payways_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "success": False,
                                "error": "Missing invoice_id.",
                                "payways": [],
                                "count": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_payways_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "success": False,
                                "error": "Client is not connected.",
                                "payways": [],
                                "count": 0
                            }
                        )

                    continue

                if data.get("type") == "provider_delete_payway":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    invoice_id = data.get("invoice_id", "")
                    sales_payway_oid = data.get("sales_payway_oid", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_payway_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "sales_payway_oid": sales_payway_oid,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "deleted_main_rows": 0,
                                "deleted_history_rows": 0
                            }
                        )
                        continue

                    if not sales_payway_oid:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_payway_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "sales_payway_oid": sales_payway_oid,
                                "success": False,
                                "error": "Missing sales_payway_oid.",
                                "deleted_main_rows": 0,
                                "deleted_history_rows": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(client_code, data)

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_payway_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "invoice_id": invoice_id,
                                "sales_payway_oid": sales_payway_oid,
                                "success": False,
                                "error": "Client is not connected.",
                                "deleted_main_rows": 0,
                                "deleted_history_rows": 0
                            }
                        )

                    continue

                if data.get("type") == "provider_delete_mydata":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    documents = data.get("documents") or []

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_mydata_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "documents": documents,
                                "deleted_success_rows": 0,
                                "deleted_response_rows": 0
                            }
                        )
                        continue

                    if not documents:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_mydata_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "No documents selected.",
                                "invoice_ids": [],
                                "deleted_success_rows": 0,
                                "deleted_response_rows": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        data
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_delete_mydata_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "documents": documents,
                                "deleted_success_rows": 0,
                                "deleted_response_rows": 0
                            }
                        )

                    continue

                if data.get("type") == "processes_get":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "processes_get_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "processes": [],
                                "count": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "processes_get",
                            "request_id": request_id,
                            "client_code": client_code
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "processes_get_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "processes": [],
                                "count": 0
                            }
                        )

                    continue

                if data.get("type") == "process_kill":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    pid = data.get("pid", "")
                    process_name = data.get("process_name", "")

                    if not request_id or not client_code or not pid:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "process_kill_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "pid": pid,
                                "process_name": process_name,
                                "error": "Missing request_id, client_code or pid."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "process_kill",
                            "request_id": request_id,
                            "client_code": client_code,
                            "pid": pid,
                            "process_name": process_name
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "process_kill_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "pid": pid,
                                "process_name": process_name,
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "client_update_check":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_check_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "current_version": "",
                                "latest_version": "",
                                "update_available": False,
                                "download_url": "",
                                "sha256": "",
                                "mandatory": False,
                                "release_notes": "",
                                "error": "Missing request_id or client_code."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "client_update_check",
                            "request_id": request_id,
                            "client_code": client_code
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_check_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "current_version": "",
                                "latest_version": "",
                                "update_available": False,
                                "download_url": "",
                                "sha256": "",
                                "mandatory": False,
                                "release_notes": "",
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "client_update_download":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")
                    download_url = data.get("download_url", "")
                    sha256 = data.get("sha256", "")
                    latest_version = data.get("latest_version", "")

                    if not request_id or not client_code or not download_url or not sha256:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_download_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "download_url": download_url,
                                "saved_path": "",
                                "file_size_bytes": 0,
                                "expected_sha256": sha256,
                                "actual_sha256": "",
                                "sha256_verified": False,
                                "latest_version": latest_version,
                                "error": "Missing request_id, client_code, download_url or sha256."
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        {
                            "type": "client_update_download",
                            "request_id": request_id,
                            "client_code": client_code,
                            "download_url": download_url,
                            "sha256": sha256,
                            "latest_version": latest_version
                        }
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "client_update_download_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "download_url": download_url,
                                "saved_path": "",
                                "file_size_bytes": 0,
                                "expected_sha256": sha256,
                                "actual_sha256": "",
                                "sha256_verified": False,
                                "latest_version": latest_version,
                                "error": "Client is not connected."
                            }
                        )

                    continue

                if data.get("type") == "provider_get_note_types":
                    request_id = data.get("request_id", "")
                    client_code = data.get("client_code", "")

                    if not request_id or not client_code:
                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_note_types_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Missing request_id or client_code.",
                                "note_types": [],
                                "count": 0
                            }
                        )
                        continue

                    self.pending_requests[request_id] = websocket

                    sent = await connection_manager.send_to_client(
                        client_code,
                        data
                    )

                    if not sent:
                        self.pending_requests.pop(request_id, None)

                        await connection_manager.send_to_dashboard(
                            websocket,
                            {
                                "type": "provider_get_note_types_result",
                                "request_id": request_id,
                                "client_code": client_code,
                                "success": False,
                                "error": "Client is not connected.",
                                "note_types": [],
                                "count": 0
                            }
                        )

                    continue

                await connection_manager.send_to_dashboard(
                    websocket,
                    {
                        "type": "echo",
                        "received": data
                    }
                )

        except WebSocketDisconnect:
            connection_manager.disconnect_dashboard(websocket)

        except Exception:
            logger.exception("Unexpected dashboard WebSocket error.")
            connection_manager.disconnect_dashboard(websocket)


websocket_routes = WebSocketRoutes()


@router.get("/api/ws-test")
def websocket_route_test(x_admin_token: str = Header(default="")) -> dict:
    """
    Προσωρινό HTTP endpoint για έλεγχο WebSocket routes.
    Προστατεύεται με admin token.
    """

    config = AppConfig()

    if x_admin_token != config.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token.")

    return {
        "success": True,
        "message": "WebSocket routes are loaded."
    }


@router.websocket("/ws/client")
async def client_websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint για client PCs.
    """

    await websocket_routes.client_socket(websocket)


@router.websocket("/ws/dashboard")
async def dashboard_websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint για dashboard.
    """

    await websocket_routes.dashboard_socket(websocket)