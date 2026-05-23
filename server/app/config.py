import os
from dotenv import load_dotenv


class AppConfig:
    """
    Κεντρική κλάση ρυθμίσεων για τον server.
    Διαβάζει τις βασικές ρυθμίσεις από το αρχείο .env.
    """

    def __init__(self) -> None:
        """
        Φορτώνει τις μεταβλητές περιβάλλοντος.
        """

        load_dotenv()

        self.app_name = os.getenv("APP_NAME", "MoonHard Remote v2 Server")
        self.app_version = os.getenv("APP_VERSION", "1.0.0")
        self.environment = os.getenv("ENVIRONMENT", "development")