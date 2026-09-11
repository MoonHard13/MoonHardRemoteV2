import logging
import re
import time
from datetime import date, datetime
from typing import Any, ClassVar

import pyodbc

logger = logging.getLogger(__name__)


class DatabaseMaintenanceService:
    """
    Εκτελεί τις ελεγχόμενες λειτουργίες συντήρησης βάσης στον client.
    Τα στοιχεία σύνδεσης χρησιμοποιούνται μόνο τοπικά και δεν επιστρέφονται ποτέ.
    """

    ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "test_connection",
            "sales_trans_info",
            "mydata_info",
            "clean_mydata",
            "history",
            "shrink",
            "rebuild",
        }
    )

    def execute(
        self,
        action: str,
        connection_string: str,
        parameters: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """Εκτελεί μία επιτρεπόμενη ενέργεια και επιστρέφει ασφαλές JSON αποτέλεσμα."""

        clean_action = str(action or "").strip().lower()
        safe_parameters = parameters if isinstance(parameters, dict) else {}

        try:
            if isinstance(timeout, bool):
                raise TypeError
            safe_timeout = max(5, min(int(timeout), 7200))
        except (TypeError, ValueError):
            return self._failure(clean_action, "Invalid database action timeout.")

        if clean_action not in self.ACTIONS:
            return self._failure(clean_action, "Unsupported database action.")

        try:
            validated_parameters = self._validate_parameters(
                clean_action, safe_parameters
            )
        except (TypeError, ValueError) as exc:
            return self._failure(clean_action, str(exc))

        started_at = time.perf_counter()
        logger.info("Έναρξη database action. action=%s", clean_action)

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)
            driver = self._get_available_sql_driver()

            with pyodbc.connect(
                odbc_connection_string,
                timeout=min(safe_timeout, 60),
                autocommit=True,
            ) as connection:
                connection.timeout = safe_timeout
                cursor = connection.cursor()
                database_name = self._database_name(cursor)
                result = self._execute_action(
                    cursor=cursor,
                    action=clean_action,
                    parameters=validated_parameters,
                    database_name=database_name,
                )

            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "Ολοκλήρωση database action. action=%s database=%s elapsed_ms=%s",
                clean_action,
                database_name,
                elapsed_ms,
            )

            return {
                "success": True,
                "error": None,
                "action": clean_action,
                "database_name": database_name,
                "driver": driver,
                "elapsed_ms": elapsed_ms,
                **result,
            }

        except Exception as exc:  # noqa: BLE001 - Οι pyodbc drivers επιστρέφουν διαφορετικούς τύπους σφαλμάτων.
            logger.error(
                "Αποτυχία database action. action=%s exception_type=%s",
                clean_action,
                type(exc).__name__,
            )
            return self._failure(
                clean_action,
                self._sanitize_error(str(exc), connection_string),
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
            )

    def _execute_action(
        self,
        cursor,
        action: str,
        parameters: dict[str, Any],
        database_name: str,
    ) -> dict[str, Any]:
        """Δρομολογεί την ενέργεια στην αντίστοιχη ελεγχόμενη SQL υλοποίηση."""

        if action == "test_connection":
            cursor.execute("SELECT @@SERVERNAME, SYSTEM_USER")
            row = cursor.fetchone()
            return {
                "message": "Database connection completed successfully.",
                "server_name": str(row[0]) if row else "",
                "login_name": str(row[1]) if row else "",
            }

        if action == "sales_trans_info":
            cursor.execute(
                "SELECT COUNT_BIG(*), MIN(SalesTransInitDate) FROM dbo.TblSnSalesTrans"
            )
            row = cursor.fetchone()
            return {
                "message": "SalesTrans information loaded successfully.",
                "total_rows": int(row[0]) if row and row[0] is not None else 0,
                "first_date": self._serialize_datetime(row[1] if row else None),
            }

        if action == "mydata_info":
            cursor.execute(
                """
                SELECT COUNT_BIG(*), MIN(MyDATA_ResponseDate)
                FROM dbo.TblSnMyDATA_Response
                WHERE MyDATA_ResponseStatusCode <> N'Success'
                """
            )
            row = cursor.fetchone()
            return {
                "message": "MyData information loaded successfully.",
                "failed_rows": int(row[0]) if row and row[0] is not None else 0,
                "first_date": self._serialize_datetime(row[1] if row else None),
            }

        if action == "clean_mydata":
            cursor.execute(
                """
                DELETE FROM dbo.TblSnMyDATA_Response
                WHERE MyDATA_ResponseStatusCode <> N'Success'
                  AND MyDATA_ResponseDate BETWEEN ? AND ?
                """,
                parameters["start_date"],
                parameters["end_date"],
            )
            deleted_rows = max(int(cursor.rowcount), 0)
            return {
                "message": "MyData cleanup completed successfully.",
                "start_date": parameters["start_date"],
                "end_date": parameters["end_date"],
                "deleted_rows": deleted_rows,
            }

        if action == "history":
            cursor.execute(
                "EXEC dbo.SnProPOS_SalesTrHist NULL, NULL, ?;",
                parameters["history_date"],
            )
            sql_messages = self._consume_all_results(cursor)
            completion_detected = any(
                "completion time" in message.lower() for message in sql_messages
            )
            return {
                "message": (
                    "Sales history completed successfully."
                    if completion_detected
                    else "Sales history finished without a completion-time SQL message."
                ),
                "history_date": parameters["history_date"],
                "completion_detected": completion_detected,
                "sql_messages": sql_messages,
            }

        if action == "shrink":
            cursor.execute(
                """
                SELECT name, type_desc
                FROM sys.database_files
                WHERE type_desc IN (N'ROWS', N'LOG')
                ORDER BY CASE WHEN type_desc = N'ROWS' THEN 0 ELSE 1 END, file_id
                """
            )
            files = cursor.fetchall()
            data_file = next(
                (str(row[0]) for row in files if str(row[1]) == "ROWS"), ""
            )
            log_file = next((str(row[0]) for row in files if str(row[1]) == "LOG"), "")

            if not data_file or not log_file:
                raise RuntimeError("Database data and log files were not both found.")

            sql_messages: list[str] = []
            cursor.execute(
                f"DBCC SHRINKDATABASE ({self._quote_identifier(database_name)})"
            )
            sql_messages.extend(self._consume_all_results(cursor))
            cursor.execute(f"DBCC SHRINKFILE ({self._quote_literal(data_file)}, 5000)")
            sql_messages.extend(self._consume_all_results(cursor))
            cursor.execute(f"DBCC SHRINKFILE ({self._quote_literal(log_file)}, 1000)")
            sql_messages.extend(self._consume_all_results(cursor))

            return {
                "message": "Database shrink completed successfully.",
                "data_file": data_file,
                "data_target_mb": 5000,
                "log_file": log_file,
                "log_target_mb": 1000,
                "sql_messages": sql_messages,
            }

        cursor.execute("EXEC dbo.spsnrebuildupdate;")
        sql_messages = self._consume_all_results(cursor)
        return {
            "message": "Database rebuild/update completed successfully.",
            "sql_messages": sql_messages,
        }

    def _validate_parameters(
        self,
        action: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Ελέγχει όλα τα δεδομένα πριν δημιουργηθεί σύνδεση SQL."""

        if action == "clean_mydata":
            start_date = self._validate_yyyymmdd(
                parameters.get("start_date"), "start_date"
            )
            end_date = self._validate_yyyymmdd(parameters.get("end_date"), "end_date")

            if start_date > end_date:
                raise ValueError("start_date must not be after end_date.")

            return {"start_date": start_date, "end_date": end_date}

        if action == "history":
            return {
                "history_date": self._validate_yyyymmdd(
                    parameters.get("history_date"),
                    "history_date",
                )
            }

        return {}

    @staticmethod
    def _validate_yyyymmdd(value: Any, field_name: str) -> str:
        """Επιστρέφει αυστηρή ημερομηνία YYYYMMDD ή απορρίπτει την τιμή."""

        if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value.strip()):
            raise ValueError(f"Invalid {field_name}. Expected YYYYMMDD.")

        clean_value = value.strip()

        try:
            date.fromisoformat(
                f"{clean_value[:4]}-{clean_value[4:6]}-{clean_value[6:8]}"
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid {field_name}. Expected a real YYYYMMDD date."
            ) from exc

        return clean_value

    @staticmethod
    def _database_name(cursor) -> str:
        """Διαβάζει το όνομα της τρέχουσας βάσης από την ενεργή σύνδεση."""

        cursor.execute("SELECT DB_NAME()")
        row = cursor.fetchone()
        database_name = str(row[0]).strip() if row and row[0] is not None else ""

        if not database_name:
            raise RuntimeError("The active database name could not be detected.")

        return database_name

    @staticmethod
    def _consume_all_results(cursor) -> list[str]:
        """Καταναλώνει όλα τα result sets και συλλέγει τα διαθέσιμα SQL μηνύματα."""

        messages: list[str] = []

        while True:
            for item in list(getattr(cursor, "messages", []) or []):
                message = (
                    item[1]
                    if isinstance(item, (tuple, list)) and len(item) > 1
                    else item
                )
                clean_message = str(message).strip()
                if clean_message and clean_message not in messages:
                    messages.append(clean_message[:2000])

            if cursor.description:
                while cursor.fetchmany(100):
                    pass

            if not cursor.nextset():
                break

        return messages[:100]

    def _to_odbc_connection_string(self, connection_string: str) -> str:
        """Μετατρέπει το connection string του BackOffice σε ODBC μορφή."""

        parts = self._parse_connection_string(connection_string)
        server = parts.get("server", "")
        database = parts.get("database", "")

        if not server:
            raise ValueError("Missing SQL Server in connection string.")
        if not database:
            raise ValueError("Missing SQL database in connection string.")

        connection_parts = [
            f"DRIVER={{{self._get_available_sql_driver()}}}",
            f"SERVER={server}",
            f"DATABASE={database}",
            f"UID={parts.get('user_id', '')}",
            f"PWD={parts.get('password', '')}",
            "Encrypt=no",
            "TrustServerCertificate=yes",
        ]
        return ";".join(connection_parts) + ";"

    @staticmethod
    def _parse_connection_string(connection_string: str) -> dict[str, str]:
        """Αναλύει τις ονομασίες πεδίων που χρησιμοποιούν SQL Server και UDL strings."""

        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password",
        }
        result: dict[str, str] = {}

        for item in str(connection_string or "").split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            mapped_key = key_map.get(re.sub(r"\s+", " ", key.strip().lower()))
            if mapped_key:
                result[mapped_key] = value.strip()

        return result

    @staticmethod
    def _get_available_sql_driver() -> str:
        """Επιλέγει τον νεότερο διαθέσιμο SQL Server ODBC driver."""

        installed_drivers = pyodbc.drivers()
        for driver in (
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ):
            if driver in installed_drivers:
                return driver
        raise RuntimeError("No compatible SQL Server ODBC driver was found.")

    @staticmethod
    def _quote_identifier(value: str) -> str:
        """Κάνει ασφαλές quoting SQL Server identifier που προήλθε από τον server."""

        return "[" + value.replace("]", "]]") + "]"

    @staticmethod
    def _quote_literal(value: str) -> str:
        """Κάνει ασφαλές quoting SQL Server Unicode literal που προήλθε από τον server."""

        return "N'" + value.replace("'", "''") + "'"

    @staticmethod
    def _serialize_datetime(value: Any) -> str | None:
        """Μετατρέπει ημερομηνίες SQL σε JSON-safe κείμενο."""

        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @classmethod
    def _sanitize_error(cls, error: str, connection_string: str) -> str:
        """Αφαιρεί connection strings και credentials από μήνυμα αποτυχίας."""

        safe_error = str(error or "Database action failed.")
        if connection_string:
            safe_error = safe_error.replace(
                str(connection_string), "[REDACTED CONNECTION]"
            )
        parsed = cls._parse_connection_string(connection_string)
        for key in ("password", "user_id"):
            secret = parsed.get(key, "")
            if secret:
                safe_error = safe_error.replace(secret, "***")
        return safe_error[:4000]

    @staticmethod
    def _failure(
        action: str, error: str, elapsed_ms: int | None = None
    ) -> dict[str, Any]:
        """Δημιουργεί κοινό αποτέλεσμα αποτυχίας χωρίς ευαίσθητα δεδομένα σύνδεσης."""

        return {
            "success": False,
            "error": error,
            "action": action,
            "database_name": "",
            "driver": None,
            "elapsed_ms": elapsed_ms,
        }
