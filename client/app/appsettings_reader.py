import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class AppSettingsReader:
    """
    Διαβάζει το appsettings.production.json από τον client υπολογιστή.

    Το read_appsettings_production() κρατάει τα πραγματικά δεδομένα μόνο τοπικά
    για SQL/Provider λειτουργίες.

    Το read_appsettings_for_server() επιστρέφει μόνο safe/masked δεδομένα
    ώστε να μη στέλνονται raw passwords, raw json ή raw text στον server.
    """

    def __init__(self) -> None:
        """
        Ορίζει τα γνωστά paths που θα ελεγχθούν.
        """

        self.known_paths: list[Path] = [
            Path(
                r"C:\Program Files (x86)\Sunsoft Ltd\ExternalTaxProvider"
                r"\External.Tax.Provider\appsettings.production.json"
            )
        ]

    def read_appsettings_production(self) -> dict[str, Any]:
        """
        Διαβάζει μόνο appsettings.production.json από γνωστό path.
        """

        for file_path in self.known_paths:
            if file_path.exists() and file_path.is_file():
                return self._read_file(file_path)

        return {
            "file_found": False,
            "file_path": None,
            "raw_json": None,
            "raw_text": None,
            "selected_bo_connection_id": 1,
            "bo_connections": [],
            "provider_connections": [],
            "appsettings_summary": {},
            "database_connection": None,
            "database_server": None,
            "database_name": None,
            "database_user": None,
            "database_password": None,
            "last_read_at": datetime.now(timezone.utc).isoformat()
        }

    def read_appsettings_for_server(self) -> dict[str, Any]:
        """
        Διαβάζει appsettings.production.json και επιστρέφει μόνο safe δεδομένα για αποστολή στον server.

        Δεν επιστρέφει:
        - raw_json
        - raw_text
        - πραγματικό password
        - πραγματικό user id
        - πραγματικό ClientAuth
        - πραγματικό subscriptionKey
        """

        local_data = self.read_appsettings_production()

        safe_bo_connections = self._sanitize_connections(
            local_data.get("bo_connections") or []
        )

        safe_provider_connections = self._sanitize_provider_connections(
            local_data.get("provider_connections") or []
        )

        database_connection = local_data.get("database_connection")
        masked_database_connection = self._mask_connection_string(database_connection)

        return {
            "file_found": local_data.get("file_found", False),
            "file_path": local_data.get("file_path"),
            "raw_json": None,
            "raw_text": None,
            "selected_bo_connection_id": local_data.get("selected_bo_connection_id", 1),
            "bo_connections": safe_bo_connections,
            "provider_connections": safe_provider_connections,
            "appsettings_summary": local_data.get("appsettings_summary") or {},
            "database_connection": masked_database_connection,
            "database_server": local_data.get("database_server"),
            "database_name": local_data.get("database_name"),
            "database_user": "***" if local_data.get("database_user") else None,
            "database_password": None,
            "has_database_password": bool(local_data.get("database_password")),
            "last_read_at": local_data.get("last_read_at")
        }

    def _read_file(self, file_path: Path) -> dict[str, Any]:
        """
        Διαβάζει και αναλύει το appsettings.production.json με ανοχή σε σχόλια και extra πληροφορίες.
        """

        logger.info("Reading appsettings.production.json: %s", file_path)

        raw_text = file_path.read_text(encoding="utf-8-sig")
        clean_text = self._clean_json_like_text(raw_text)
        raw_json = json.loads(clean_text)

        app_settings = self._find_first_dict_by_key(raw_json, "AppSettings") or {}

        bo_connections = self._find_first_list_by_key(raw_json, "BOConnections")
        provider_connections = self._find_first_list_by_key(raw_json, "ProviderConnections")

        selected_bo_connection_id = 1
        selected_bo_connection = self._get_bo_connection_by_id(
            bo_connections=bo_connections,
            selected_id=selected_bo_connection_id
        )

        database_connection = None

        if selected_bo_connection:
            database_connection = selected_bo_connection.get("DatabaseConnection")

        connection_parts = self._parse_connection_string(database_connection)

        appsettings_summary = {
            "AllowedHosts": self._find_first_value_by_key(raw_json, "AllowedHosts"),
            "MaxRetries": app_settings.get("MaxRetries") if isinstance(app_settings, dict) else None,
            "MaxWaitTimePerInvoice": app_settings.get("MaxWaitTimePerInvoice") if isinstance(app_settings, dict) else None,
            "initialDate": app_settings.get("initialDate") if isinstance(app_settings, dict) else None,
            "BOConnectionIDs": [item.get("ID") for item in bo_connections if isinstance(item, dict)],
            "ProviderConnectionIDs": [item.get("ID") for item in provider_connections if isinstance(item, dict)],
        }

        return {
            "file_found": True,
            "file_path": str(file_path),
            "raw_json": raw_json,
            "raw_text": raw_text,
            "selected_bo_connection_id": selected_bo_connection_id,
            "bo_connections": bo_connections,
            "provider_connections": provider_connections,
            "appsettings_summary": appsettings_summary,
            "database_connection": database_connection,
            "database_server": connection_parts.get("server"),
            "database_name": connection_parts.get("database"),
            "database_user": connection_parts.get("user_id"),
            "database_password": connection_parts.get("password"),
            "last_read_at": datetime.now(timezone.utc).isoformat()
        }

    def _sanitize_connections(self, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Κρύβει sensitive values από BO/FO connections πριν σταλούν στον server.
        """

        safe_connections: list[dict[str, Any]] = []

        for connection in connections:
            if not isinstance(connection, dict):
                continue

            safe_connection: dict[str, Any] = {}

            for key, value in connection.items():
                key_lower = str(key).strip().lower()

                if key_lower in ("password", "pwd", "clientauth", "clientauthfo", "subscriptionkey"):
                    safe_connection[key] = "***" if value else ""
                    continue

                if key_lower == "databaseconnection":
                    safe_connection[key] = self._mask_connection_string(str(value) if value else "")
                    continue

                safe_connection[key] = value

            database_connection = connection.get("DatabaseConnection")
            connection_parts = self._parse_connection_string(
                str(database_connection) if database_connection else None
            )

            safe_connection["DatabaseServer"] = connection_parts.get("server")
            safe_connection["DatabaseName"] = connection_parts.get("database")
            safe_connection["HasDatabaseUser"] = bool(connection_parts.get("user_id"))
            safe_connection["HasDatabasePassword"] = bool(connection_parts.get("password"))

            safe_connections.append(safe_connection)

        return safe_connections

    def _sanitize_provider_connections(self, provider_connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Επιστρέφει ProviderConnections χωρίς credentials.
        Τα URLs δεν θεωρούνται password, αλλά κρατάμε μόνο τα βασικά πεδία.
        """

        safe_provider_connections: list[dict[str, Any]] = []

        for provider_connection in provider_connections:
            if not isinstance(provider_connection, dict):
                continue

            safe_provider_connections.append(
                {
                    "ID": provider_connection.get("ID"),
                    "BaseURL": provider_connection.get("BaseURL"),
                    "OfflineURL": provider_connection.get("OfflineURL")
                }
            )

        return safe_provider_connections

    def _mask_connection_string(self, connection_string: str | None) -> str | None:
        """
        Κρύβει User ID / UID / Password / PWD μέσα από SQL connection string.
        Κρατάει Server και Database ώστε να εμφανίζονται στο dashboard.
        """

        if not connection_string:
            return None

        masked_parts: list[str] = []

        for item in str(connection_string).split(";"):
            if not item:
                continue

            if "=" not in item:
                masked_parts.append(item)
                continue

            key, value = item.split("=", 1)
            normalized_key = self._normalize_connection_key(key)

            if normalized_key in ("user_id", "password"):
                masked_parts.append(f"{key}=***")
            else:
                masked_parts.append(f"{key}={value}")

        return ";".join(masked_parts) + ";"

    def _clean_json_like_text(self, text: str) -> str:
        """
        Καθαρίζει JSON-like αρχείο από σχόλια και trailing commas χωρίς να χαλάει strings.
        """

        without_block_comments = self._remove_block_comments(text)
        without_line_comments = self._remove_line_comments(without_block_comments)
        without_trailing_commas = self._remove_trailing_commas(without_line_comments)

        return without_trailing_commas

    def _remove_line_comments(self, text: str) -> str:
        """
        Αφαιρεί // σχόλια μόνο όταν βρίσκονται εκτός string.
        Δεν πειράζει URLs όπως https:// μέσα σε string.
        """

        result: list[str] = []
        index = 0
        in_string = False
        escape_next = False

        while index < len(text):
            current_char = text[index]
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if escape_next:
                result.append(current_char)
                escape_next = False
                index += 1
                continue

            if current_char == "\\" and in_string:
                result.append(current_char)
                escape_next = True
                index += 1
                continue

            if current_char == '"':
                in_string = not in_string
                result.append(current_char)
                index += 1
                continue

            if not in_string and current_char == "/" and next_char == "/":
                while index < len(text) and text[index] not in ("\r", "\n"):
                    index += 1
                continue

            result.append(current_char)
            index += 1

        return "".join(result)

    def _remove_block_comments(self, text: str) -> str:
        """
        Αφαιρεί /* ... */ σχόλια μόνο όταν βρίσκονται εκτός string.
        """

        result: list[str] = []
        index = 0
        in_string = False
        escape_next = False

        while index < len(text):
            current_char = text[index]
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if escape_next:
                result.append(current_char)
                escape_next = False
                index += 1
                continue

            if current_char == "\\" and in_string:
                result.append(current_char)
                escape_next = True
                index += 1
                continue

            if current_char == '"':
                in_string = not in_string
                result.append(current_char)
                index += 1
                continue

            if not in_string and current_char == "/" and next_char == "*":
                index += 2

                while index + 1 < len(text):
                    if text[index] == "*" and text[index + 1] == "/":
                        index += 2
                        break

                    index += 1

                continue

            result.append(current_char)
            index += 1

        return "".join(result)

    def _remove_trailing_commas(self, text: str) -> str:
        """
        Αφαιρεί trailing commas πριν από } ή ].
        """

        return re.sub(r",\s*([}\]])", r"\1", text)

    def _find_first_dict_by_key(self, data: Any, target_key: str) -> dict[str, Any] | None:
        """
        Ψάχνει αναδρομικά για dictionary με συγκεκριμένο key.
        """

        found_value = self._find_first_value_by_key(data, target_key)

        if isinstance(found_value, dict):
            return found_value

        return None

    def _find_first_list_by_key(self, data: Any, target_key: str) -> list[dict[str, Any]]:
        """
        Ψάχνει αναδρομικά για λίστα με συγκεκριμένο key.
        """

        found_value = self._find_first_value_by_key(data, target_key)

        if not isinstance(found_value, list):
            return []

        return [
            item
            for item in found_value
            if isinstance(item, dict)
        ]

    def _find_first_value_by_key(self, data: Any, target_key: str) -> Any:
        """
        Ψάχνει αναδρομικά για τιμή με συγκεκριμένο key, ανεξάρτητα από θέση στο JSON.
        """

        if isinstance(data, dict):
            for key, value in data.items():
                if str(key).lower() == target_key.lower():
                    return value

            for value in data.values():
                found_value = self._find_first_value_by_key(value, target_key)

                if found_value is not None:
                    return found_value

        if isinstance(data, list):
            for item in data:
                found_value = self._find_first_value_by_key(item, target_key)

                if found_value is not None:
                    return found_value

        return None
        
    def _extract_list_from_appsettings(
        self,
        raw_json: dict[str, Any],
        key: str
    ) -> list[dict[str, Any]]:
        """
        Εξάγει λίστα από AppSettings με βάση το key.
        """

        app_settings = raw_json.get("AppSettings", {})

        if not isinstance(app_settings, dict):
            return []

        value = app_settings.get(key, [])

        if not isinstance(value, list):
            return []

        return value

    def _get_bo_connection_by_id(
        self,
        bo_connections: list[dict[str, Any]],
        selected_id: int
    ) -> dict[str, Any] | None:
        """
        Επιλέγει BOConnection με βάση το ID.
        Default είναι ID = 1.
        """

        for connection in bo_connections:
            if connection.get("ID") == selected_id:
                return connection

        return bo_connections[0] if bo_connections else None

    def _parse_connection_string(self, connection_string: str | None) -> dict[str, str | None]:
        """
        Αναλύει connection string SQL Server σε βασικά πεδία.
        """

        if not connection_string:
            return {
                "server": None,
                "database": None,
                "user_id": None,
                "password": None
            }

        parts: dict[str, str] = {}

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = self._normalize_connection_key(key)

            parts[normalized_key] = value.strip()

        return {
            "server": parts.get("server"),
            "database": parts.get("database"),
            "user_id": parts.get("user_id"),
            "password": parts.get("password")
        }

    def _normalize_connection_key(self, key: str) -> str:
        """
        Κανονικοποιεί τα ονόματα πεδίων ενός SQL connection string.
        """

        normalized = re.sub(r"\s+", " ", key.strip().lower())

        mapping = {
            "server": "server",
            "data source": "server",
            "address": "server",
            "addr": "server",
            "network address": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "user": "user_id",
            "password": "password",
            "pwd": "password"
        }

        return mapping.get(normalized, normalized)