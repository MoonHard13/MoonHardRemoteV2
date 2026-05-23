import asyncio
import json
import socket
import getpass

import websockets


class ClientWebSocketTester:
    """
    Δοκιμαστικός WebSocket client για έλεγχο σύνδεσης client PC με Render server.
    """

    def __init__(self, websocket_url: str) -> None:
        """
        Αρχικοποιεί το WebSocket URL.
        """

        self.websocket_url = websocket_url

    async def run_test(self) -> None:
        """
        Συνδέεται στο WebSocket και στέλνει register μήνυμα.
        """

        print(f"Connecting to: {self.websocket_url}")

        async with websockets.connect(self.websocket_url) as websocket:
            register_message = {
                "type": "register",
                "client_code": "TEST-REAL-CLIENT-001",
                "display_name": "Test Real Client",
                "pc_name": socket.gethostname(),
                "username": getpass.getuser(),
                "app_version": "1.0.0"
            }

            await websocket.send(json.dumps(register_message))

            response = await websocket.recv()
            print("Server response:")
            print(response)

            test_message = {
                "type": "ping",
                "message": "Hello from test client"
            }

            await websocket.send(json.dumps(test_message))

            echo_response = await websocket.recv()
            print("Server echo response:")
            print(echo_response)

            print("Keeping connection open for 10 seconds...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    tester = ClientWebSocketTester(
        "wss://moonhardremotev2.onrender.com/ws/client"
    )

    asyncio.run(tester.run_test())