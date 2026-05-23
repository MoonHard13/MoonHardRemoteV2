import logging
from supabase import Client, create_client

from app.config import AppConfig


logger = logging.getLogger(__name__)


class SupabaseDatabase:
    """
    Κεντρική κλάση σύνδεσης με Supabase.
    Χρησιμοποιείται μόνο από τον server.
    """

    def __init__(self) -> None:
        """
        Δημιουργεί τον Supabase client.
        """

        self.config = AppConfig()
        self.config.validate_supabase_config()

        self.client: Client = create_client(
            self.config.supabase_url,
            self.config.supabase_service_role_key
        )

        logger.info("Supabase client initialized successfully.")

    def get_client(self) -> Client:
        """
        Επιστρέφει τον Supabase client για χρήση από repositories/services.
        """

        return self.client


database = SupabaseDatabase()