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
    Αποθηκεύει όλα τα δεδομένα χωρίς masking.
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
            "database_connection": None,
            "database_server": None,
            "database_name": None,
            "database_user": None,
            "database_password": None,
            "last_read_at": datetime.now(timezone.utc).isoformat()
        }

    def _read_file(self, file_path: Path) -> dict[str, Any]:
        """
        Διαβάζει και αναλύει το appsettings.production.json.
        """

        logger.info("Reading appsettings.production.json: %s", file_path)

        raw_text = file_path.read_text(encoding="utf-8-sig")
        raw_json = json.loads(raw_text)

        database_connection = self._extract_database_connection(raw_json)
        connection_parts = self._parse_connection_string(database_connection)

        return {
            "file_found": True,
            "file_path": str(file_path),
            "raw_json": raw_json,
            "raw_text": raw_text,
            "database_connection": database_connection,
            "database_server": connection_parts.get("server"),
            "database_name": connection_parts.get("database"),
            "database_user": connection_parts.get("user_id"),
            "database_password": connection_parts.get("password"),
            "last_read_at": datetime.now(timezone.utc).isoformat()
        }

    def _extract_database_connection(self, raw_json: dict[str, Any]) -> str | None:
        """
        Εξάγει το BOConnections[0].DatabaseConnection αν υπάρχει.
        """

        bo_connections = raw_json.get("BOConnections")

        if not isinstance(bo_connections, list) or not bo_connections:
            return None

        first_connection = bo_connections[0]

        if not isinstance(first_connection, dict):
            return None

        return first_connection.get("DatabaseConnection")

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