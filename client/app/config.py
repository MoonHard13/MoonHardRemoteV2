import os
from pathlib import Path
from dotenv import load_dotenv


class ClientConfig:
    """
    Κεντρική κλάση ρυθμίσεων για τον MoonHard Remote Client.
    """

    def __init__(self) -> None:
        """
        Φορτώνει τις βασικές ρυθμίσεις του client.
        """

        load_dotenv()

        self.app_name = "MoonHard Remote v2 Client"
        self.app_version = "1.0.0"
        self.client_token = os.getenv("41c3fa81b8156eb832371fb93c7b0d4d", "")
        
        self.server_websocket_url = os.getenv(
            "SERVER_WEBSOCKET_URL",
            "wss://moonhardremotev2.onrender.com/ws/client"
        )

        self.server_websocket_url = os.getenv(
            "SERVER_WEBSOCKET_URL",
            "wss://moonhardremotev2.onrender.com/ws/client"
        )

        self.client_token = os.getenv("CLIENT_TOKEN", "")

        self.program_data_dir = Path(
            os.getenv(
                "MOONHARD_CLIENT_DATA_DIR",
                r"C:\ProgramData\MoonHardRemoteV2"
            )
        )

        self.identity_file = self.program_data_dir / "client_identity.json"
        self.log_dir = self.program_data_dir / "logs"
        self.reconnect_seconds = 5
        self.heartbeat_seconds = 30