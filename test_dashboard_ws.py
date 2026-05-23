import asyncio
import json

import websockets


class DashboardWebSocketTester:
    """
    Δοκιμαστικός WebSocket client για έλεγχο σύνδεσης dashboard με Render server.
    """

    def __init__(self, websocket_url: str) -> None:
        """
        Αρχικοποιεί το URL του WebSocket.
        """

        self.websocket_url = websocket_url

    async def run_test(self) -> None:
        """
        Συνδέεται στο WebSocket και διαβάζει τα πρώτα μηνύματα του server.
        """

        print(f"Connecting to: {self.websocket_url}")

        async with websockets.connect(self.websocket_url) as websocket:
            connected_message = await websocket.recv()
            print("\nServer connected message:")
            print(connected_message)

            clients_message = await websocket.recv()
            print("\nServer clients list message:")
            print(clients_message)

            clients_payload = json.loads(clients_message)

            if clients_payload.get("type") == "clients_list":
                print(f"\nClients count: {clients_payload.get('count')}")

                for client in clients_payload.get("clients", []):
                    print(
                        f"- {client.get('client_code')} | "
                        f"{client.get('pc_name')} | "
                        f"{client.get('status')} | "
                        f"{client.get('last_seen')}"
                    )

            test_message = {
                "type": "test",
                "message": "Hello from dashboard tester"
            }

            await websocket.send(json.dumps(test_message))

            response = await websocket.recv()
            print("\nServer echo response:")
            print(response)


if __name__ == "__main__":
    tester = DashboardWebSocketTester(
        "wss://moonhardremotev2.onrender.com/ws/dashboard"
    )

    asyncio.run(tester.run_test())