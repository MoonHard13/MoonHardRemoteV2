import logging
from typing import Any

from app.database import database


logger = logging.getLogger(__name__)


class ClientRepository:
    """
    Repository για τις ενέργειες του πίνακα clients.
    Όλη η επικοινωνία με Supabase για clients περνάει από εδώ.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί τον Supabase client.
        """

        self.db = database.get_client()

    def get_all_clients(self) -> list[dict[str, Any]]:
        """
        Επιστρέφει όλους τους clients από τη βάση.
        """

        logger.info("Fetching all clients from Supabase.")

        response = (
            self.db
            .table("clients")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def upsert_test_client(self) -> dict[str, Any]:
        """
        Δημιουργεί ή ενημερώνει έναν δοκιμαστικό client.
        Χρησιμοποιείται μόνο για έλεγχο της σύνδεσης με Supabase.
        """

        logger.info("Upserting test client into Supabase.")

        test_client_data = {
            "client_code": "TEST-CLIENT-001",
            "display_name": "Test Client",
            "pc_name": "TEST-PC",
            "username": "testuser",
            "app_version": "1.0.0",
            "status": "online"
        }

        response = (
            self.db
            .table("clients")
            .upsert(test_client_data, on_conflict="client_code")
            .execute()
        )

        if not response.data:
            raise RuntimeError("Test client upsert returned no data.")

        return response.data[0]

    def delete_test_client(self) -> dict[str, Any]:
        """
        Διαγράφει τον δοκιμαστικό client από τη βάση.
        """

        logger.info("Deleting test client from Supabase.")

        response = (
            self.db
            .table("clients")
            .delete()
            .eq("client_code", "TEST-CLIENT-001")
            .execute()
        )

        return {
            "deleted": True,
            "data": response.data or []
        }