import hashlib
import json
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
        Αρχικοποιεί τον Supabase client και τα process-local optimization caches.
        """

        self.db = database.get_client()
        self._appsettings_payload_hashes: dict[str, str] = {}
        self._appsettings_payload_cache: dict[str, dict[str, Any]] = {}
        self._appsettings_cache_loaded = False

    def get_all_clients(self) -> list[dict[str, Any]]:
        """
        Επιστρέφει μικρή λίστα clients για το Dashboard μαζί με group info.
        Δεν χρησιμοποιούμε select("*") για μείωση Supabase egress.
        """

        logger.info("Fetching dashboard clients list from Supabase view.")

        response = (
            self.db
            .table("v_clients_dashboard")
            .select(
                "id, client_code, display_name, pc_name, username, app_version, "
                "status, last_seen, connected_at, disconnected_at, created_at, "
                "group_id, group_name, group_color, group_sort_order, "
                "amv_version, bo_version, etp_version, aws_version"
            )
            .order("group_sort_order", desc=False)
            .order("group_name", desc=False)
            .order("created_at", desc=True)
            .execute()
        )

        return response.data or []

    def get_client_by_code(self, client_code: str) -> dict[str, Any] | None:
        """
        Επιστρέφει έναν client από το dashboard view με group/program version info.
        Χρησιμοποιείται για targeted dashboard refresh ενός μόνο client.
        """

        if not client_code:
            return None

        response = (
            self.db
            .table("v_clients_dashboard")
            .select(
                "id, client_code, display_name, pc_name, username, app_version, "
                "status, last_seen, connected_at, disconnected_at, created_at, "
                "group_id, group_name, group_color, group_sort_order, "
                "amv_version, bo_version, etp_version, aws_version"
            )
            .eq("client_code", client_code)
            .limit(1)
            .execute()
        )

        data = response.data or []

        if not data:
            return None

        return data[0]

    def get_client_groups(self) -> list[dict[str, Any]]:
        """
        Επιστρέφει όλα τα διαθέσιμα client groups.
        """

        logger.info("Fetching client groups from Supabase.")

        response = (
            self.db
            .table("client_groups")
            .select("id, name, description, color, sort_order, is_default, created_at")
            .order("sort_order", desc=False)
            .order("name", desc=False)
            .execute()
        )

        return response.data or []

    def get_default_group_id(self) -> str:
        """
        Επιστρέφει το id του default group Ungrouped.
        Αν δεν υπάρχει, το δημιουργεί.
        """

        response = (
            self.db
            .table("client_groups")
            .select("id")
            .eq("name", "Ungrouped")
            .limit(1)
            .execute()
        )

        data = response.data or []

        if data:
            return str(data[0]["id"])

        created_response = (
            self.db
            .table("client_groups")
            .insert({
                "name": "Ungrouped",
                "description": "Default group for clients without assigned group.",
                "color": "#64748B",
                "sort_order": 0,
                "is_default": True
            })
            .execute()
        )

        if not created_response.data:
            raise RuntimeError("Failed to create default Ungrouped group.")

        return str(created_response.data[0]["id"])

    def get_or_create_client_group(self, group_name: str) -> dict[str, Any]:
        """
        Βρίσκει group με βάση το όνομα ή το δημιουργεί αν δεν υπάρχει.
        """

        clean_name = group_name.strip()

        if not clean_name:
            clean_name = "Ungrouped"

        existing_response = (
            self.db
            .table("client_groups")
            .select("id, name, description, color, sort_order, is_default, created_at")
            .eq("name", clean_name)
            .limit(1)
            .execute()
        )

        existing_data = existing_response.data or []

        if existing_data:
            return existing_data[0]

        logger.info("Creating new client group: %s", clean_name)

        created_response = (
            self.db
            .table("client_groups")
            .insert({
                "name": clean_name,
                "description": None,
                "color": "#64748B",
                "sort_order": 100,
                "is_default": False
            })
            .execute()
        )

        if not created_response.data:
            raise RuntimeError("Failed to create client group.")

        return created_response.data[0]

    def update_client_group(self, client_code: str, group_name: str) -> dict[str, Any]:
        """
        Ενημερώνει το group ενός client.
        Αν το group δεν υπάρχει, δημιουργείται αυτόματα.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        group = self.get_or_create_client_group(group_name)
        group_id = group.get("id")

        if not group_id:
            raise RuntimeError("Client group has no id.")

        logger.info(
            "Updating client group. client_code=%s group_name=%s group_id=%s",
            client_code,
            group.get("name"),
            group_id
        )

        response = (
            self.db
            .table("clients")
            .update({
                "group_id": group_id
            })
            .eq("client_code", client_code)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Client group update returned no data.")

        return {
            "client": response.data[0],
            "group": group
        }

    def create_client_group(self, group_name: str) -> dict[str, Any]:
        """
        Δημιουργεί νέο client group.
        Αν υπάρχει ήδη, επιστρέφει το υπάρχον.
        """

        clean_name = group_name.strip()

        if not clean_name:
            raise ValueError("Group name cannot be empty.")

        return self.get_or_create_client_group(clean_name)

    def rename_client_group(self, group_id: str, new_name: str) -> dict[str, Any]:
        """
        Μετονομάζει ένα client group.
        Δεν επιτρέπει rename του default Ungrouped group.
        """

        if not group_id:
            raise ValueError("Missing group_id.")

        clean_name = new_name.strip()

        if not clean_name:
            raise ValueError("Group name cannot be empty.")

        existing_group_response = (
            self.db
            .table("client_groups")
            .select("id, name, is_default")
            .eq("id", group_id)
            .limit(1)
            .execute()
        )

        existing_groups = existing_group_response.data or []

        if not existing_groups:
            raise RuntimeError("Group not found.")

        existing_group = existing_groups[0]

        if existing_group.get("is_default"):
            raise ValueError("Cannot rename the default Ungrouped group.")

        logger.info(
            "Renaming client group. group_id=%s new_name=%s",
            group_id,
            clean_name
        )

        response = (
            self.db
            .table("client_groups")
            .update({
                "name": clean_name
            })
            .eq("id", group_id)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Client group rename returned no data.")

        return response.data[0]

    def delete_client_group(self, group_id: str) -> dict[str, Any]:
        """
        Διαγράφει ένα client group.
        Όσοι clients ανήκουν σε αυτό μεταφέρονται πρώτα στο Ungrouped.
        Δεν επιτρέπει delete του default Ungrouped group.
        """

        if not group_id:
            raise ValueError("Missing group_id.")

        existing_group_response = (
            self.db
            .table("client_groups")
            .select("id, name, is_default")
            .eq("id", group_id)
            .limit(1)
            .execute()
        )

        existing_groups = existing_group_response.data or []

        if not existing_groups:
            raise RuntimeError("Group not found.")

        existing_group = existing_groups[0]

        if existing_group.get("is_default"):
            raise ValueError("Cannot delete the default Ungrouped group.")

        default_group_id = self.get_default_group_id()

        logger.info(
            "Moving clients from group_id=%s to Ungrouped group_id=%s before delete.",
            group_id,
            default_group_id
        )

        self.db.table("clients").update({
            "group_id": default_group_id
        }).eq("group_id", group_id).execute()

        logger.info("Deleting client group. group_id=%s", group_id)

        response = (
            self.db
            .table("client_groups")
            .delete()
            .eq("id", group_id)
            .execute()
        )

        return {
            "deleted": True,
            "group_id": group_id,
            "group": existing_group,
            "data": response.data or []
        }

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

    def get_client_security_record(self, client_code: str) -> dict[str, Any] | None:
        """
        Επιστρέφει τα security fields ενός client για authentication.
        """

        if not client_code:
            return None

        response = (
            self.db
            .table("clients")
            .select(
                "id, client_code, display_name, group_id, "
                "client_token_hash, client_token_revoked, client_token_version, "
                "client_token_last_seen_at"
            )
            .eq("client_code", client_code)
            .limit(1)
            .execute()
        )

        data = response.data or []

        if not data:
            return None

        return data[0]

    def set_client_instance_token_hash(
        self,
        client_code: str,
        client_token_hash: str
    ) -> dict[str, Any]:
        """
        Αποθηκεύει hash του per-client token.
        Δεν αποθηκεύει ποτέ το raw token.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        if not client_token_hash:
            raise ValueError("Missing client_token_hash.")

        now_utc = datetime.now(timezone.utc).isoformat()

        logger.info("Registering per-client token hash for client: %s", client_code)

        response = (
            self.db
            .table("clients")
            .update(
                {
                    "client_token_hash": client_token_hash,
                    "client_token_registered_at": now_utc,
                    "client_token_last_seen_at": now_utc,
                    "client_token_version": 1,
                    "client_token_revoked": False
                }
            )
            .eq("client_code", client_code)
            .execute()
        )

        return response.data[0] if response.data else {}

    def should_touch_client_token_last_seen(
        self,
        security_record: dict[str, Any] | None,
        min_interval_hours: int = 24
    ) -> bool:
        """
        Ελέγχει αν το audit timestamp του per-client token χρειάζεται refresh.

        Ο έλεγχος γίνεται πάνω στο security record που ήδη διαβάστηκε στο register,
        ώστε να μην απαιτείται επιπλέον Supabase GET.
        """

        if not security_record:
            return False

        raw_last_seen = security_record.get("client_token_last_seen_at")

        if not raw_last_seen:
            return True

        try:
            normalized_value = str(raw_last_seen).replace("Z", "+00:00")
            last_seen = datetime.fromisoformat(normalized_value)

            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)

            elapsed_seconds = (
                datetime.now(timezone.utc) - last_seen.astimezone(timezone.utc)
            ).total_seconds()

            return elapsed_seconds >= max(1, min_interval_hours) * 3600

        except (TypeError, ValueError):
            logger.warning(
                "Invalid client_token_last_seen_at value. A refresh will be persisted."
            )
            return True

    def touch_client_token_last_seen(self, client_code: str) -> None:
        """
        Ενημερώνει χειροκίνητα το token audit timestamp.

        Παραμένει διαθέσιμο για συμβατότητα, αλλά το normal register flow
        συγχωνεύει το timestamp στο ήδη απαραίτητο client UPDATE.
        """

        if not client_code:
            return

        now_utc = datetime.now(timezone.utc).isoformat()

        (
            self.db
            .table("clients")
            .update(
                {
                    "client_token_last_seen_at": now_utc
                }
            )
            .eq("client_code", client_code)
            .execute()
        )

    def reset_client_instance_token(
        self,
        client_code: str,
        reason: str = "manual_reset"
    ) -> dict[str, Any]:
        """
        Κάνει reset το per-client token hash.

        Δεν δημιουργεί νέο token στον server.
        Στο επόμενο reconnect ο client θα πάρει TOKEN_RESET_REQUIRED,
        θα δημιουργήσει νέο local token και θα ξανακάνει bootstrap.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        security_record = self.get_client_security_record(client_code)

        if not security_record:
            raise RuntimeError("Client was not found.")

        current_version = int(security_record.get("client_token_version") or 1)
        next_version = current_version + 1

        logger.warning(
            "Resetting per-client token. client_code=%s next_version=%s reason=%s",
            client_code,
            next_version,
            reason
        )

        response = (
            self.db
            .table("clients")
            .update(
                {
                    "client_token_hash": None,
                    "client_token_registered_at": None,
                    "client_token_last_seen_at": None,
                    "client_token_version": next_version,
                    "client_token_revoked": False
                }
            )
            .eq("client_code", client_code)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Client token reset returned no data.")

        return response.data[0]

    def upsert_connected_client(
        self,
        client_data: dict[str, Any],
        existing_client_record: dict[str, Any] | None = None,
        existing_client_checked: bool = False,
        touch_token_last_seen: bool = False
    ) -> dict[str, Any]:
        """
        Δημιουργεί ή ενημερώνει έναν πραγματικό client που συνδέθηκε μέσω WebSocket.

        Όταν το authentication flow έχει ήδη διαβάσει τον client, επαναχρησιμοποιεί
        εκείνο το record και αποφεύγει δεύτερο GET /rest/v1/clients.
        """

        client_code = client_data.get("client_code")

        if not client_code:
            raise ValueError("Missing client_code.")

        logger.info("Upserting connected client: %s", client_code)

        now_utc = datetime.now(timezone.utc).isoformat()

        if existing_client_checked:
            existing_clients = (
                [existing_client_record]
                if existing_client_record
                else []
            )
        else:
            existing_response = (
                self.db
                .table("clients")
                .select("id, display_name, group_id")
                .eq("client_code", client_code)
                .execute()
            )

            existing_clients = existing_response.data or []

        if existing_clients:
            update_payload = {
                "pc_name": client_data.get("pc_name", "UNKNOWN-PC"),
                "username": client_data.get("username"),
                "app_version": client_data.get("app_version"),
                "amv_version": client_data.get("amv_version"),
                "bo_version": client_data.get("bo_version"),
                "etp_version": client_data.get("etp_version"),
                "aws_version": client_data.get("aws_version"),
                "status": "online",
                "last_seen": now_utc,
                "connected_at": now_utc,
                "disconnected_at": None
            }

            if touch_token_last_seen:
                update_payload["client_token_last_seen_at"] = now_utc

            response = (
                self.db
                .table("clients")
                .update(update_payload)
                .eq("client_code", client_code)
                .execute()
            )
        else:
            default_group_id = self.get_default_group_id()   
                    
            response = (
                self.db
                .table("clients")
                .insert({
                    "client_code": client_code,
                    "display_name": client_data.get("display_name") or client_data.get("pc_name"),
                    "pc_name": client_data.get("pc_name", "UNKNOWN-PC"),
                    "username": client_data.get("username"),
                    "app_version": client_data.get("app_version"),
                    "amv_version": client_data.get("amv_version"),
                    "bo_version": client_data.get("bo_version"),
                    "etp_version": client_data.get("etp_version"),
                    "aws_version": client_data.get("aws_version"),
                    "status": "online",
                    "last_seen": now_utc,
                    "connected_at": now_utc,
                    "disconnected_at": None,
                    "group_id": default_group_id
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
    
    def _build_safe_appsettings_payload(
        self,
        appsettings_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Δημιουργεί το safe payload που επιτρέπεται να αποθηκευτεί στη Supabase.
        """

        client_code = appsettings_data.get("client_code")

        if not client_code:
            raise ValueError("Missing client_code.")

        return {
            "client_code": client_code,
            "file_found": appsettings_data.get("file_found", False),
            "file_path": appsettings_data.get("file_path"),
            "raw_json": None,
            "raw_text": None,
            "database_connection": appsettings_data.get("database_connection"),
            "database_server": appsettings_data.get("database_server"),
            "database_name": appsettings_data.get("database_name"),
            "database_user": None,
            "database_password": None,
            "last_read_at": appsettings_data.get("last_read_at"),
            "selected_bo_connection_id": appsettings_data.get("selected_bo_connection_id", 1),
            "bo_connections": appsettings_data.get("bo_connections") or [],
            "provider_connections": appsettings_data.get("provider_connections") or [],
            "appsettings_summary": appsettings_data.get("appsettings_summary") or {}
        }

    def _get_appsettings_payload_hash(self, payload: dict[str, Any]) -> str:
        """
        Υπολογίζει σταθερό hash μόνο από τις πραγματικές ρυθμίσεις.

        Το last_read_at εξαιρείται επίτηδες, επειδή αλλάζει σε κάθε reconnect
        ακόμα και όταν το AppSettings περιεχόμενο είναι ακριβώς το ίδιο.
        """

        comparable_keys = (
            "client_code",
            "file_found",
            "file_path",
            "database_connection",
            "database_server",
            "database_name",
            "selected_bo_connection_id",
            "bo_connections",
            "provider_connections",
            "appsettings_summary",
        )

        comparable_payload = {
            key: payload.get(key)
            for key in comparable_keys
        }

        serialized_payload = json.dumps(
            comparable_payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str
        )

        return hashlib.sha256(
            serialized_payload.encode("utf-8")
        ).hexdigest()

    def _ensure_appsettings_cache_loaded(self) -> None:
        """
        Φορτώνει μία φορά τα αποθηκευμένα safe AppSettings στη μνήμη του server.

        Έτσι μετά από Render restart γίνεται ένα μόνο bulk GET αντί να ξαναγράφει
        κάθε client τα ίδια AppSettings στη Supabase κατά το reconnect.
        """

        if self._appsettings_cache_loaded:
            return

        logger.info("Priming AppSettings comparison cache from Supabase.")

        response = (
            self.db
            .table("client_appsettings")
            .select(
                "id, client_code, file_found, file_path, "
                "database_connection, database_server, database_name, "
                "last_read_at, selected_bo_connection_id, "
                "bo_connections, provider_connections, appsettings_summary"
            )
            .execute()
        )

        for saved_payload in response.data or []:
            client_code = str(saved_payload.get("client_code") or "").strip()

            if not client_code:
                continue

            payload_hash = self._get_appsettings_payload_hash(saved_payload)
            self._appsettings_payload_hashes[client_code] = payload_hash
            self._appsettings_payload_cache[client_code] = saved_payload

        self._appsettings_cache_loaded = True

        logger.info(
            "AppSettings comparison cache primed. clients=%s",
            len(self._appsettings_payload_hashes)
        )

    def upsert_client_appsettings(self, appsettings_data: dict[str, Any]) -> dict[str, Any]:
        """
        Αποθηκεύει safe/masked AppSettings μόνο όταν έχουν πραγματικά αλλάξει.

        Το cache είναι process-local και γίνεται prime με ένα bulk GET μετά από
        server restart. Έτσι τα reconnects με αμετάβλητο AppSettings δεν
        δημιουργούν redundant Supabase POST requests.
        """

        self._ensure_appsettings_cache_loaded()

        safe_payload = self._build_safe_appsettings_payload(appsettings_data)
        client_code = str(safe_payload["client_code"])
        payload_hash = self._get_appsettings_payload_hash(safe_payload)
        cached_hash = self._appsettings_payload_hashes.get(client_code)

        if cached_hash == payload_hash:
            logger.debug(
                "Skipping unchanged appsettings Supabase upsert. client_code=%s",
                client_code
            )

            cached_payload = self._appsettings_payload_cache.get(
                client_code,
                safe_payload
            )

            return {
                **cached_payload,
                "_write_skipped": True
            }

        logger.info("Saving changed safe appsettings for client: %s", client_code)

        response = (
            self.db
            .table("client_appsettings")
            .upsert(
                safe_payload,
                on_conflict="client_code"
            )
            .execute()
        )

        if not response.data:
            raise RuntimeError("Appsettings upsert returned no data.")

        saved_payload = response.data[0]
        self._appsettings_payload_hashes[client_code] = payload_hash
        self._appsettings_payload_cache[client_code] = saved_payload

        return saved_payload


    def get_client_appsettings(self, client_code: str) -> dict[str, Any]:
        """
        Επιστρέφει safe/masked AppSettings από το in-memory cache.

        Το cache γίνεται prime με ένα bulk Supabase GET ανά server process και
        ενημερώνεται σε κάθε πραγματική αλλαγή AppSettings.
        """

        if not client_code:
            raise ValueError("Missing client_code.")

        self._ensure_appsettings_cache_loaded()

        cached_data = self._appsettings_payload_cache.get(client_code)

        if not cached_data:
            return {
                "client_code": client_code,
                "file_found": False,
                "message": "No appsettings saved for this client yet."
            }

        safe_data = dict(cached_data)
        safe_data["raw_json"] = None
        safe_data["raw_text"] = None
        safe_data["database_user"] = None
        safe_data["database_password"] = None

        return safe_data


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