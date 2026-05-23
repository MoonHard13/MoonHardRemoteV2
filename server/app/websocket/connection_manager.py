import logging
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Κεντρικός διαχειριστής WebSocket συνδέσεων.
    Κρατάει προσωρινά τις ενεργές συνδέσεις dashboard και clients στη μνήμη του server.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί τις λίστες ενεργών συνδέσεων.
        """

        self.dashboard_connections: list[WebSocket] = []
        self.client_connections: dict[str, WebSocket] = {}

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        """
        Αποδέχεται και αποθηκεύει μια νέα WebSocket σύνδεση dashboard.
        """

        await websocket.accept()
        self.dashboard_connections.append(websocket)

        logger.info(
            "Dashboard connected. Active dashboards: %s",
            len(self.dashboard_connections)
        )

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        """
        Αφαιρεί μια WebSocket σύνδεση dashboard από τις ενεργές συνδέσεις.
        """

        if websocket in self.dashboard_connections:
            self.dashboard_connections.remove(websocket)

        logger.info(
            "Dashboard disconnected. Active dashboards: %s",
            len(self.dashboard_connections)
        )

    async def connect_client(self, client_code: str, websocket: WebSocket) -> None:
        """
        Αποθηκεύει μια ήδη αποδεκτή WebSocket σύνδεση client.
        Το accept γίνεται μέσα στο client_socket, πριν ληφθεί το πρώτο register μήνυμα.
        """

        self.client_connections[client_code] = websocket

        logger.info(
            "Client connected: %s. Active clients: %s",
            client_code,
            len(self.client_connections)
        )

    def disconnect_client(self, client_code: str) -> None:
        """
        Αφαιρεί έναν client από τις ενεργές WebSocket συνδέσεις.
        """

        if client_code in self.client_connections:
            del self.client_connections[client_code]

        logger.info(
            "Client disconnected: %s. Active clients: %s",
            client_code,
            len(self.client_connections)
        )

    async def send_to_dashboard(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """
        Στέλνει μήνυμα JSON σε ένα συγκεκριμένο dashboard.
        """

        await websocket.send_json(message)

    async def broadcast_to_dashboards(self, message: dict[str, Any]) -> None:
        """
        Στέλνει μήνυμα JSON σε όλα τα ενεργά dashboards.
        Αν κάποιο dashboard έχει αποσυνδεθεί, αφαιρείται από τη λίστα.
        """

        disconnected_dashboards: list[WebSocket] = []

        for dashboard_websocket in self.dashboard_connections:
            try:
                await dashboard_websocket.send_json(message)
            except Exception:
                logger.exception("Failed to send message to dashboard.")
                disconnected_dashboards.append(dashboard_websocket)

        for dashboard_websocket in disconnected_dashboards:
            self.disconnect_dashboard(dashboard_websocket)

    def get_connected_client_count(self) -> int:
        """
        Επιστρέφει τον αριθμό των ενεργών client WebSocket συνδέσεων.
        """

        return len(self.client_connections)

    def get_connected_dashboard_count(self) -> int:
        """
        Επιστρέφει τον αριθμό των ενεργών dashboard WebSocket συνδέσεων.
        """

        return len(self.dashboard_connections)


connection_manager = ConnectionManager()