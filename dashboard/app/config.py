import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def resource_path(relative_path: str) -> Path:
    """
    Επιστρέφει σωστό path για αρχεία είτε τρέχουμε από source είτε από PyInstaller exe.
    """

    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path

    return Path(__file__).resolve().parents[1] / relative_path


class DashboardConfig:
    """
    Κεντρική κλάση ρυθμίσεων για το MoonHard Remote Dashboard.
    """

    def __init__(self) -> None:
        """
        Φορτώνει τις βασικές ρυθμίσεις του dashboard.
        """

        programdata_env = Path(r"C:\ProgramData\MoonHardRemoteV2\Dashboard\.env")
        bundled_env = resource_path(".env")

        if programdata_env.exists():
            load_dotenv(programdata_env, override=True)
        elif bundled_env.exists():
            load_dotenv(bundled_env, override=True)
        else:
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