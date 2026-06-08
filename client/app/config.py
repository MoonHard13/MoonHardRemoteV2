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

        self._load_environment()

        self.app_name = "MoonHard Remote v2 Client"
        self.app_version = "1.0.7"
        self.client_token = os.getenv("CLIENT_TOKEN", "")
        
        self.server_websocket_url = os.getenv(
            "SERVER_WEBSOCKET_URL",
            "wss://moonhardremotev2.onrender.com/ws/client"
        )

        self.program_data_dir = Path(
            os.getenv(
                "MOONHARD_CLIENT_DATA_DIR",
                r"C:\ProgramData\MoonHardRemoteV2"
            )
        )

        self.identity_file = self.program_data_dir / "client_identity.json"
        self.log_dir = self.program_data_dir / "logs"
        self.reconnect_initial_seconds = 3
        self.reconnect_max_seconds = 30
        self.reconnect_reset_after_success_seconds = 60

        self.heartbeat_seconds = 25
        self.websocket_open_timeout_seconds = 20
        self.websocket_ping_interval_seconds = 20
        self.websocket_ping_timeout_seconds = 20
        self.server_wake_url = os.getenv(
            "SERVER_WAKE_URL",
            "https://moonhardremotev2.onrender.com/api/ws-test"
        )
        
    def _load_environment(self) -> None:
        """
        Φορτώνει μεταβλητές περιβάλλοντος από ασφαλείς πιθανές τοποθεσίες.
        """

        possible_env_paths = [
            Path.cwd() / ".env",
            Path(r"C:\ProgramData\MoonHardRemoteV2") / ".env"
        ]

        for env_path in possible_env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                return

        load_dotenv()