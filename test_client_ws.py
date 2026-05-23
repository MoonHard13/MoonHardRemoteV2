import asyncio
import json

import websockets


class DashboardWebSocketTester:
    """
    Δοκιμαστικός WebSocket client για έλεγχο live ενημερώσεων dashboard.
    """

    def __init__(self, websocket_url: str) -> None:
        """
        Αρχικοποιεί το WebSocket URL.
        """

        self.websocket_url = websocket_url

    async def run_test(self) -> None:
        """
        Συνδέεται στο dashboard WebSocket και εμφανίζει όλα τα μηνύματα που λαμβάνει.
        """

        print(f"Connecting to: {self.websocket_url}")

        async with websockets.connect(self.websocket_url) as websocket:
            print("Dashboard connected. Waiting for server messages...\n")

            while True:
                message = await websocket.recv()
                payload = json.loads(message)

                print("=" * 80)
                print(f"Message type: {payload.get('type')}")
                print(json.dumps(payload, indent=4, ensure_ascii=False))

                if payload.get("type") == "clients_list":
                    print("\nClients:")
                    for client in payload.get("clients", []):
                        print(
                            f"- {client.get('client_code')} | "
                            f"{client.get('pc_name')} | "
                            f"{client.get('status')} | "
                            f"{client.get('last_seen')}"
                        )

                print("=" * 80)


if __name__ == "__main__":
    tester = DashboardWebSocketTester(
        "wss://moonhardremotev2.onrender.com/ws/dashboard"
    )

    asyncio.run(tester.run_test())