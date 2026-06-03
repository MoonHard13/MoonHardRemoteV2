from pathlib import Path


class UpdaterConfig:
    """
    Κεντρική κλάση ρυθμίσεων για το MoonHard updater.
    """

    def __init__(self) -> None:
        """
        Ορίζει τα βασικά paths και ονόματα service.
        """

        self.service_name = "MoonHardRemoteClient"

        self.install_dir = Path(
            r"C:\Program Files\MoonHardRemoteV2\Client"
        )

        self.program_data_dir = Path(
            r"C:\ProgramData\MoonHardRemoteV2"
        )

        self.updates_dir = self.program_data_dir / "updates"
        self.extracted_dir = self.updates_dir / "extracted"
        self.backup_dir = self.updates_dir / "backup"
        self.logs_dir = self.program_data_dir / "logs"

        self.client_exe_name = "MoonHardRemoteClient.exe"
        self.required_items = [
            "MoonHardRemoteClient.exe",
            "_internal"
        ]