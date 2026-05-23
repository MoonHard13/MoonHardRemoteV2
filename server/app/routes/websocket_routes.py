import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.connection_manager import connection_manager
from app.repositories.client_repository import ClientRepository


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
        
    async def client_socket(self, websocket: WebSocket) -> None:
        """
        WebSocket endpoint για client PCs.
        Ο client συνδέεται, στέλνει register μήνυμα και αποθηκεύεται στη βάση.
        """

        client_code = ""

        try:
            await websocket.accept()

            first_message = await websocket.receive_json()

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

            while True:
                data = await websocket.receive_json()

                logger.info("Client message received from %s: %s", client_code, data)

                await websocket.send_json({
                    "type": "echo",
                    "received": data
                })

        except WebSocketDisconnect:
            logger.info("Client WebSocket disconnected: %s", client_code)

            if client_code:
                connection_manager.disconnect_client(client_code)
                self.client_repository.mark_client_offline(client_code)

        except Exception:
            logger.exception("Unexpected client WebSocket error.")

            if client_code:
                connection_manager.disconnect_client(client_code)
                self.client_repository.mark_client_offline(client_code)       

    async def dashboard_socket(self, websocket: WebSocket) -> None:
        """
        Δοκιμαστικό WebSocket endpoint για dashboard.
        Αποδέχεται σύνδεση και απαντάει σε test μηνύματα.
        """

        await connection_manager.connect_dashboard(websocket)

        try:
            await connection_manager.send_to_dashboard(
                websocket,
                {
                    "type": "dashboard_connected",
                    "message": "Dashboard WebSocket connected successfully."
                }
            )

            while True:
                data = await websocket.receive_json()

                logger.info("Dashboard message received: %s", data)

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
def websocket_route_test() -> dict:
    """
    Προσωρινό HTTP endpoint για να ελέγξουμε ότι φορτώθηκε το websocket_routes.py.
    """

    return {
        "success": True,
        "message": "websocket_routes.py loaded successfully",
        "dashboard_ws": "/ws/dashboard"
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