import asyncio
import json
import os
import uuid

from dotenv import load_dotenv
import websockets


class DashboardTerminalCommandTester:
    """
    Δοκιμαστικό dashboard script για αποστολή terminal command σε client.
    """

    def __init__(self) -> None:
        """
        Φορτώνει ρυθμίσεις από dashboard/.env.
        """

        load_dotenv("dashboard/.env")

        self.websocket_url = os.getenv(
            "DASHBOARD_WEBSOCKET_URL",
            "wss://moonhardremotev2.onrender.com/ws/dashboard"
        )
        self.dashboard_token = os.getenv("DASHBOARD_TOKEN", "")

    async def run_test(self) -> None:
        """
        Συνδέεται ως dashboard και στέλνει δοκιμαστική terminal εντολή.
        """

        client_code = input("Client code: ").strip()
        command = input("Command: ").strip() or "dir"

        command_id = str(uuid.uuid4())

        async with websockets.connect(self.websocket_url) as websocket:
            await websocket.send(json.dumps({
                "type": "authenticate",
                "token": self.dashboard_token
            }))

            while True:
                message = await websocket.recv()
                payload = json.loads(message)

                print("SERVER:", json.dumps(payload, indent=4, ensure_ascii=False))

                if payload.get("type") == "clients_list":
                    break

            await websocket.send(json.dumps({
                "type": "terminal_command",
                "command_id": command_id,
                "client_code": client_code,
                "shell": "cmd",
                "command": command
            }))

            while True:
                message = await websocket.recv()
                payload = json.loads(message)

                print("SERVER:", json.dumps(payload, indent=4, ensure_ascii=False))

                if payload.get("type") in ("terminal_result", "terminal_error"):
                    break


if __name__ == "__main__":
    tester = DashboardTerminalCommandTester()
    asyncio.run(tester.run_test())