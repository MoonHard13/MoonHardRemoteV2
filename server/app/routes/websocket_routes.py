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
        self.pending_terminal_commands: dict[str, WebSocket] = {}

    async def broadcast_clients_list(self) -> None:
        """
        Στέλνει την τρέχουσα λίστα clients σε όλα τα ενεργά dashboards.
        """

        clients = self.client_repository.get_all_clients()

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

                if data.get("type") == "terminal_result":
                    command_id = data.get("command_id", "")

                    dashboard_websocket = self.pending_terminal_commands.pop(
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

            clients = self.client_repository.get_all_clients()

            await connection_manager.send_to_dashboard(
                websocket,
                {
                    "type": "clients_list",
                    "count": len(clients),
                    "clients": clients
                }
            )

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
                                "message": "Missing command_id, client_code or command."
                            }
                        )
                        continue

                    self.pending_terminal_commands[command_id] = websocket

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
                        self.pending_terminal_commands.pop(command_id, None)

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
        raise HTTPException(status_code=401, detail="Unauthorized.")

    return {
        "success": True,
        "message": "websocket_routes.py loaded successfully",
        "dashboard_ws": "/ws/dashboard",
        "client_ws": "/ws/client"
    }


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint για dashboard.
    """

    await websocket_routes.dashboard_socket(websocket)


@router.websocket("/ws/client")
async def client_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint για client PCs.
    """

    await websocket_routes.client_socket(websocket)