import logging
import re
from typing import Any

import pyodbc


logger = logging.getLogger(__name__)


class SqlExecutor:
    """
    Εκτελεί SQL Server queries στον client υπολογιστή χρησιμοποιώντας BOConnection από appsettings.production.json.
    """

    def execute_sql(
        self,
        connection_string: str,
        sql_text: str,
        timeout: int = 60
    ) -> dict[str, Any]:
        """
        Εκτελεί SQL script και επιστρέφει αποτελέσματα.
        Υποστηρίζει batches με GO.
        """

        clean_sql = sql_text.strip()

        if not clean_sql:
            return {
                "success": False,
                "error": "SQL text is empty.",
                "batches": []
            }

        batches = self._split_sql_batches(clean_sql)
        results: list[dict[str, Any]] = []

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            logger.info("Connecting to SQL Server for SQL execution.")

            with pyodbc.connect(odbc_connection_string, timeout=timeout, autocommit=True) as connection:
                cursor = connection.cursor()

                for index, batch in enumerate(batches, start=1):
                    if not batch.strip():
                        continue

                    logger.info("Executing SQL batch %s/%s", index, len(batches))

                    batch_result = self._execute_batch(cursor, batch, index)
                    results.append(batch_result)

            return {
                "success": True,
                "error": None,
                "batches": results
            }

        except Exception as exc:
            logger.exception("SQL execution failed.")

            return {
                "success": False,
                "error": str(exc),
                "batches": results
            }

    def _execute_batch(self, cursor, batch: str, batch_index: int) -> dict[str, Any]:
        """
        Εκτελεί ένα SQL batch και μαζεύει όλα τα result sets.
        """

        batch_data: dict[str, Any] = {
            "batch_index": batch_index,
            "sql": batch,
            "result_sets": [],
            "rowcount": None,
            "error": None
        }

        try:
            cursor.execute(batch)

            while True:
                if cursor.description:
                    columns = [column[0] for column in cursor.description]
                    rows = cursor.fetchall()

                    serialized_rows = [
                        [self._serialize_value(value) for value in row]
                        for row in rows
                    ]

                    batch_data["result_sets"].append(
                        {
                            "columns": columns,
                            "rows": serialized_rows,
                            "row_count": len(serialized_rows)
                        }
                    )
                else:
                    batch_data["rowcount"] = cursor.rowcount

                if not cursor.nextset():
                    break

            return batch_data

        except Exception as exc:
            logger.exception("SQL batch failed.")

            batch_data["error"] = str(exc)
            return batch_data

    def _split_sql_batches(self, sql_text: str) -> list[str]:
        """
        Χωρίζει SQL script σε batches με βάση γραμμές GO.
        """

        batches: list[str] = []
        current_lines: list[str] = []

        for line in sql_text.splitlines():
            if re.match(r"^\s*GO\s*;?\s*$", line, flags=re.IGNORECASE):
                batches.append("\n".join(current_lines))
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            batches.append("\n".join(current_lines))

        return batches

    def _to_odbc_connection_string(self, connection_string: str) -> str:
        """
        Μετατρέπει SQL Server connection string σε ODBC connection string.
        Υποστηρίζει SQL Server 2012 μέχρι νεότερες εκδόσεις, ανάλογα με τον διαθέσιμο ODBC driver.
        """

        parts = self._parse_connection_string(connection_string)

        server = parts.get("server", "")
        database = parts.get("database", "")
        user_id = parts.get("user_id", "")
        password = parts.get("password", "")

        trust_server_certificate = self._normalize_yes_no_value(
            parts.get("trustservercertificate"),
            default="yes"
        )

        if not server:
            raise ValueError("Missing SQL Server in connection string.")

        if not database:
            raise ValueError("Missing SQL database in connection string.")

        driver = self._get_available_sql_driver()

        connection_parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
            f"UID={user_id}",
            f"PWD={password}",
            "Encrypt=no",
            f"TrustServerCertificate={trust_server_certificate}",
        ]

        return ";".join(connection_parts) + ";"

    def _get_available_sql_driver(self) -> str:
        """
        Επιλέγει τον καλύτερο διαθέσιμο SQL Server ODBC driver.
        """

        installed_drivers = pyodbc.drivers()

        preferred_drivers = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]

        for driver in preferred_drivers:
            if driver in installed_drivers:
                return driver

        raise RuntimeError(
            "No SQL Server ODBC driver found. Install Microsoft ODBC Driver 17 or 18 for SQL Server."
        )

    def _parse_connection_string(self, connection_string: str) -> dict[str, str]:
        """
        Αναλύει SQL Server connection string σε dictionary.
        """

        result: dict[str, str] = {}

        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password",
            "trustservercertificate": "trustservercertificate"
        }

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = re.sub(r"\s+", " ", key.strip().lower())
            mapped_key = key_map.get(normalized_key, normalized_key)

            result[mapped_key] = value.strip()

        return result

    def _serialize_value(self, value) -> str:
        """
        Μετατρέπει SQL values σε strings για αποστολή μέσω JSON.
        """

        if value is None:
            return ""

        return str(value)
    
    def _normalize_yes_no_value(self, value: str | None, default: str = "yes") -> str:
        """
        Μετατρέπει boolean-like τιμές σε yes/no για ODBC connection string.
        """

        if value is None:
            return default

        normalized = str(value).strip().lower()

        if normalized in ("true", "yes", "1", "y"):
            return "yes"

        if normalized in ("false", "no", "0", "n"):
            return "no"

        return default