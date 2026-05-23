import os
from dotenv import load_dotenv


class AppConfig:
    """
    Κεντρική κλάση ρυθμίσεων για τον server.
    Διαβάζει τις βασικές ρυθμίσεις από το αρχείο .env ή από τα Render Environment Variables.
    """

    def __init__(self) -> None:
        """
        Φορτώνει τις μεταβλητές περιβάλλοντος.
        """

        load_dotenv()

        self.app_name = os.getenv("APP_NAME", "MoonHard Remote v2 Server")
        self.app_version = os.getenv("APP_VERSION", "1.0.0")
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.client_token = os.getenv("CLIENT_TOKEN", "")
        self.dashboard_token = os.getenv("DASHBOARD_TOKEN", "")
        self.admin_token = os.getenv("ADMIN_TOKEN", "")

        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    def validate_supabase_config(self) -> None:
        """
        Ελέγχει αν υπάρχουν οι απαραίτητες ρυθμίσεις για σύνδεση με Supabase.
        """

        if not self.supabase_url:
            raise ValueError("Missing SUPABASE_URL environment variable.")

        if not self.supabase_service_role_key:
            raise ValueError("Missing SUPABASE_SERVICE_ROLE_KEY environment variable.")
        
    def validate_security_config(self) -> None:
        """
        Ελέγχει αν υπάρχουν τα απαραίτητα tokens ασφαλείας.
        """

        if not self.client_token:
            raise ValueError("Missing CLIENT_TOKEN environment variable.")

        if not self.dashboard_token:
            raise ValueError("Missing DASHBOARD_TOKEN environment variable.")

        if not self.admin_token:
            raise ValueError("Missing ADMIN_TOKEN environment variable.")