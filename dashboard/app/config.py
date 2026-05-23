import os
from pathlib import Path
from dotenv import load_dotenv


class DashboardConfig:
    """
    Κεντρική κλάση ρυθμίσεων για το MoonHard Remote Dashboard.
    """

    def __init__(self) -> None:
        """
        Φορτώνει τις βασικές ρυθμίσεις του dashboard.
        """

        load_dotenv()

        self.app_name = "MoonHard Remote v2 Dashboard"
        self.app_version = "1.0.0"
        self.dashboard_token = os.getenv("DASHBOARD_TOKEN", "")

        self.dashboard_websocket_url = os.getenv(
            "DASHBOARD_WEBSOCKET_URL",
            "wss://moonhardremotev2.onrender.com/ws/dashboard"
        )

        self.local_data_dir = Path(
            os.getenv(
                "MOONHARD_DASHBOARD_DATA_DIR",
                r"C:\ProgramData\MoonHardRemoteV2\Dashboard"
            )
        )

        self.log_dir = self.local_data_dir / "logs"