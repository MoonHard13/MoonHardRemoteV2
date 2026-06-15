import logging
from typing import Any
from datetime import datetime, timezone

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
            .select(
                "id, client_code, display_name, pc_name, username, app_version, "
                "status, last_seen, connected_at, disconnected_at, created_at"
            )
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

    def upsert_connected_client(self, client_data: dict[str, Any]) -> dict[str, Any]:
        """
        Δημιουργεί ή ενημερώνει έναν πραγματικό client που συνδέθηκε μέσω WebSocket.
        Αν ο client υπάρχει ήδη, δεν αλλάζει ποτέ το display_name.
        """

        client_code = client_data.get("client_code")

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Upserting connected client: %s", client_code)

        now_utc = datetime.now(timezone.utc).isoformat()

        existing_response = (
            self.db
            .table("clients")
            .select("id, display_name")
            .eq("client_code", client_code)
            .execute()
        )

        existing_clients = existing_response.data or []

        if existing_clients:
            response = (
                self.db
                .table("clients")
                .update({
                    "pc_name": client_data.get("pc_name", "UNKNOWN-PC"),
                    "username": client_data.get("username"),
                    "app_version": client_data.get("app_version"),
                    "status": "online",
                    "last_seen": now_utc,
                    "connected_at": now_utc,
                    "disconnected_at": None
                })
                .eq("client_code", client_code)
                .execute()
            )
        else:
            response = (
                self.db
                .table("clients")
                .insert({
                    "client_code": client_code,
                    "display_name": client_data.get("display_name") or client_data.get("pc_name"),
                    "pc_name": client_data.get("pc_name", "UNKNOWN-PC"),
                    "username": client_data.get("username"),
                    "app_version": client_data.get("app_version"),
                    "status": "online",
                    "last_seen": now_utc,
                    "connected_at": now_utc,
                    "disconnected_at": None
                })
                .execute()
            )

        if not response.data:
            raise RuntimeError("Client upsert returned no data.")

        return response.data[0]

    def mark_client_offline(self, client_code: str) -> dict[str, Any]:
        """
        Σημειώνει έναν client ως offline όταν κλείσει η WebSocket σύνδεση.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Marking client offline: %s", client_code)

        now_utc = datetime.now(timezone.utc).isoformat()

        response = (
            self.db
            .table("clients")
            .update({
                "status": "offline",
                "disconnected_at": now_utc,
                "last_seen": now_utc
            })
            .eq("client_code", client_code)
            .execute()
        )

        return response.data[0] if response.data else {}
    
    def update_client_heartbeat(self, client_code: str) -> dict[str, Any]:
        """
        Ενημερώνει το last_seen ενός client που παραμένει συνδεδεμένος.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Updating heartbeat for client: %s", client_code)

        now_utc = datetime.now(timezone.utc).isoformat()

        response = (
            self.db
            .table("clients")
            .update({
                "status": "online",
                "last_seen": now_utc
            })
            .eq("client_code", client_code)
            .execute()
        )

        return response.data[0] if response.data else {}

    def rename_client(self, client_code: str, display_name: str) -> dict[str, Any]:
        """
        Ενημερώνει το φιλικό όνομα ενός client στη βάση.
        Δεν αλλάζει το πραγματικό Windows pc_name.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        clean_display_name = display_name.strip()

        if not clean_display_name:
            raise ValueError("Display name cannot be empty.")

        logger.info(
            "Renaming client %s to display_name=%s",
            client_code,
            clean_display_name
        )

        response = (
            self.db
            .table("clients")
            .update({
                "display_name": clean_display_name
            })
            .eq("client_code", client_code)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Client rename returned no data.")

        return response.data[0]
    
    def upsert_client_appsettings(self, appsettings_data: dict[str, Any]) -> dict[str, Any]:
        """
        Αποθηκεύει το appsettings.production.json του client στη βάση.
        Περιλαμβάνει όλα τα raw δεδομένα χωρίς masking.
        """

        client_code = appsettings_data.get("client_code")

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Saving appsettings for client: %s", client_code)

        response = (
            self.db
            .table("client_appsettings")
            .upsert(
                {
                    "client_code": client_code,
                    "file_found": appsettings_data.get("file_found", False),
                    "file_path": appsettings_data.get("file_path"),
                    "raw_json": appsettings_data.get("raw_json"),
                    "raw_text": appsettings_data.get("raw_text"),
                    "database_connection": appsettings_data.get("database_connection"),
                    "database_server": appsettings_data.get("database_server"),
                    "database_name": appsettings_data.get("database_name"),
                    "database_user": appsettings_data.get("database_user"),
                    "database_password": appsettings_data.get("database_password"),
                    "last_read_at": appsettings_data.get("last_read_at"),
                    "selected_bo_connection_id": appsettings_data.get("selected_bo_connection_id", 1),
                    "bo_connections": appsettings_data.get("bo_connections"),
                    "provider_connections": appsettings_data.get("provider_connections"),
                    "appsettings_summary": appsettings_data.get("appsettings_summary")
                },
                on_conflict="client_code"
            )
            .execute()
        )

        if not response.data:
            raise RuntimeError("Appsettings upsert returned no data.")

        return response.data[0]
    
    def get_client_appsettings(self, client_code: str) -> dict[str, Any]:
        """
        Επιστρέφει τα αποθηκευμένα appsettings.production.json για συγκεκριμένο client.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Fetching appsettings for client: %s", client_code)

        response = (
            self.db
            .table("client_appsettings")
            .select("*")
            .eq("client_code", client_code)
            .execute()
        )

        data = response.data or []

        if not data:
            return {
                "client_code": client_code,
                "file_found": False,
                "message": "No appsettings saved for this client yet."
            }

        return data[0]
    
    def delete_client(self, client_code: str) -> dict[str, Any]:
        """
        Διαγράφει έναν client από τη βάση με βάση το client_code.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Deleting client from database: %s", client_code)

        response = (
            self.db
            .table("clients")
            .delete()
            .eq("client_code", client_code)
            .execute()
        )

        return {
            "deleted": True,
            "client_code": client_code,
            "data": response.data or []
        }