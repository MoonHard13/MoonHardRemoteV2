import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.connection_manager import connection_manager


router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


class WebSocketRoutes:
    """
    Routes για WebSocket επικοινωνία.
    Προς το παρόν περιέχει μόνο test dashboard WebSocket.
    """

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