from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = PROJECT_ROOT / "senario_prosorinon.py"
TARGET_FILE = PROJECT_ROOT / "client" / "app" / "senario_prosorinon_service.py"


def extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """
    Εξάγει κομμάτι κώδικα ανάμεσα σε δύο markers.
    """

    start_index = text.index(start_marker)
    end_index = text.index(end_marker, start_index)

    return text[start_index:end_index].strip()


def main() -> None:
    """
    Δημιουργεί καθαρό MoonHard service module από το standalone πρόγραμμα.
    """

    source_text = SOURCE_FILE.read_text(encoding="utf-8")

    models_section = extract_section(
        source_text,
        "# ==========================================================\n# Models",
        "# ==========================================================\n# UDL Reader"
    )

    odbc_section = extract_section(
        source_text,
        "# ==========================================================\n# ODBC Driver helper",
        "# ==========================================================\n# Database connection"
    )

    sql_checks_section = extract_section(
        source_text,
        "# ==========================================================\n# SQL checks",
        "# ==========================================================\n# CLI application"
    )

    output = f'''import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pyodbc


logger = logging.getLogger(__name__)


class AppLogger:
    """
    Lightweight logger adapter για τους ελέγχους σε MoonHard client service.
    """

    @staticmethod
    def info(message: str) -> None:
        logger.info(message)

    @staticmethod
    def error(message: str) -> None:
        logger.error(message)

    @staticmethod
    def exception(message: str) -> None:
        logger.exception(message)


{models_section}


{odbc_section}


{sql_checks_section}


class SenarioProsorinonService:
    """
    Εκτελεί τους ελέγχους Σεναρίου Προσωρινών Αποδείξεων
    χρησιμοποιώντας DatabaseConnection από BOConnection.
    """

    def run_checks(
        self,
        database_connection: str,
        timeout: int = 60
    ) -> dict[str, Any]:
        """
        Εκτελεί όλους τους ελέγχους και επιστρέφει serializable αποτέλεσμα για dashboard.
        """

        if not database_connection:
            return {{
                "success": False,
                "database_name": "",
                "total": 0,
                "success_count": 0,
                "problem_count": 0,
                "results": [],
                "error": "DatabaseConnection is empty."
            }}

        connection = None

        try:
            odbc_connection_string = self._to_odbc_connection_string(database_connection)
            connection = pyodbc.connect(odbc_connection_string, timeout=timeout)

            database_name = self._get_database_name(connection)

            checks = SqlChecks(connection)
            check_results = checks.run_all_checks(include_schema_check=True)

            serialized_results = [
                {{
                    "success": bool(result.success),
                    "title": str(result.title),
                    "message": str(result.message)
                }}
                for result in check_results
            ]

            success_count = sum(1 for result in serialized_results if result["success"])
            problem_count = len(serialized_results) - success_count

            return {{
                "success": True,
                "database_name": database_name,
                "total": len(serialized_results),
                "success_count": success_count,
                "problem_count": problem_count,
                "results": serialized_results,
                "error": ""
            }}

        except Exception as exc:
            logger.exception("Senario Prosorinon checks failed.")

            return {{
                "success": False,
                "database_name": "",
                "total": 0,
                "success_count": 0,
                "problem_count": 0,
                "results": [],
                "error": str(exc)
            }}

        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    logger.exception("Failed to close Senario Prosorinon SQL connection.")

    def _get_database_name(self, connection) -> str:
        """
        Επιστρέφει το όνομα της ενεργής βάσης.
        """

        cursor = connection.cursor()
        cursor.execute("SELECT DB_NAME()")
        row = cursor.fetchone()

        if row and row[0]:
            return str(row[0])

        return ""

    def _to_odbc_connection_string(self, connection_string: str) -> str:
        """
        Μετατρέπει SQL Server connection string από appsettings σε ODBC connection string.
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

        driver = OdbcDriverHelper.get_best_driver()

        connection_parts = [
            f"DRIVER={{{{driver}}}}",
            f"SERVER={{server}}",
            f"DATABASE={{database}}",
            "Encrypt=no",
            f"TrustServerCertificate={{trust_server_certificate}}",
        ]

        if user_id or password:
            connection_parts.append(f"UID={{user_id}}")
            connection_parts.append(f"PWD={{password}}")
        else:
            connection_parts.append("Trusted_Connection=yes")

        return ";".join(connection_parts) + ";"

    def _parse_connection_string(self, connection_string: str) -> dict[str, str]:
        """
        Αναλύει SQL Server connection string σε dictionary.
        """

        result: dict[str, str] = {{}}

        key_map = {{
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password",
            "trustservercertificate": "trustservercertificate"
        }}

        for item in connection_string.split(";"):
            if "=" not in item:
                continue

            key, value = item.split("=", 1)
            normalized_key = re.sub(r"\\s+", " ", key.strip().lower())
            mapped_key = key_map.get(normalized_key, normalized_key)

            result[mapped_key] = value.strip()

        return result

    def _normalize_yes_no_value(self, value: str | None, default: str = "yes") -> str:
        """
        Μετατρέπει boolean-like τιμές σε yes/no για ODBC.
        """

        if value is None:
            return default

        normalized = str(value).strip().lower()

        if normalized in ("true", "yes", "1", "y"):
            return "yes"

        if normalized in ("false", "no", "0", "n"):
            return "no"

        return default
'''

    TARGET_FILE.write_text(output, encoding="utf-8")
    print(f"Created: {TARGET_FILE}")


if __name__ == "__main__":
    main()