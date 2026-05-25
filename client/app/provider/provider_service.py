import logging
import re
from typing import Any

import pyodbc

from app.provider.provider_models import ProviderInvoiceRow


logger = logging.getLogger(__name__)


class ProviderService:
    """
    Client-side Provider/MUPT service.
    Εκτελεί αναζητήσεις στη βάση του client PC.
    Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
    """

    def search_invoices(
        self,
        connection_string: str,
        start_yyyymmdd: str,
        end_yyyymmdd: str,
        afm_filter: str = "",
        invoice_type_filter: str = "",
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Αναζητά παραστατικά όπως το MUPT, χρησιμοποιώντας BOConnection από appsettings.production.json.
        """

        start = start_yyyymmdd.strip()
        end = end_yyyymmdd.strip()
        afm = afm_filter.strip()
        invoice_type = invoice_type_filter.strip()

        if not self._is_valid_yyyymmdd(start):
            return {
                "success": False,
                "error": "Invalid start_date. Expected YYYYMMDD.",
                "invoices": [],
                "count": 0,
                "table": None
            }

        if not self._is_valid_yyyymmdd(end):
            return {
                "success": False,
                "error": "Invalid end_date. Expected YYYYMMDD.",
                "invoices": [],
                "count": 0,
                "table": None
            }

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                invoice_table = self._detect_invoice_table(cursor)

                invoices = self._fetch_invoices(
                    cursor=cursor,
                    table=invoice_table,
                    start_yyyymmdd=start,
                    end_yyyymmdd=end,
                    afm_filter=afm,
                    invoice_type_filter=invoice_type
                )

            invoice_dicts = [invoice.to_dict() for invoice in invoices]

            return {
                "success": True,
                "error": None,
                "invoices": invoice_dicts,
                "count": len(invoice_dicts),
                "table": invoice_table
            }

        except Exception as exc:
            logger.exception("Provider invoice search failed.")

            return {
                "success": False,
                "error": str(exc),
                "invoices": [],
                "count": 0,
                "table": None
            }

    def _detect_invoice_table(self, cursor) -> str:
        """
        Εντοπίζει ποιο view παραστατικών υπάρχει στη βάση.
        Προτεραιότητα: VSnMyDATAInvoicesAMV και μετά VSnMyDATAInvoices.
        """

        if self._table_exists(cursor, "VSnMyDATAInvoicesAMV"):
            return "VSnMyDATAInvoicesAMV"

        if self._table_exists(cursor, "VSnMyDATAInvoices"):
            return "VSnMyDATAInvoices"

        raise RuntimeError(
            "Δεν υπάρχει ούτε το VSnMyDATAInvoicesAMV ούτε το VSnMyDATAInvoices."
        )

    def _fetch_invoices(
        self,
        cursor,
        table: str,
        start_yyyymmdd: str,
        end_yyyymmdd: str,
        afm_filter: str = "",
        invoice_type_filter: str = ""
    ) -> list[ProviderInvoiceRow]:
        """
        Φέρνει παραστατικά με ίδια λογική φίλτρων όπως το MUPT.
        """

        where_parts = [
            "CONVERT(date, issueDate) BETWEEN CONVERT(date, ?, 112) AND CONVERT(date, ?, 112)"
        ]
        params: list[Any] = [start_yyyymmdd, end_yyyymmdd]

        if afm_filter:
            if afm_filter.isdigit() and len(afm_filter) >= 5:
                where_parts.append("CAST(CustAFM AS NVARCHAR(32)) = ?")
                params.append(afm_filter)
            else:
                where_parts.append("CAST(CustAFM AS NVARCHAR(32)) LIKE ?")
                params.append(f"%{afm_filter}%")

        if invoice_type_filter:
            normalized_invoice_type = invoice_type_filter.replace(",", ".")
            where_parts.append("CAST(invoiceType AS NVARCHAR(64)) LIKE ?")
            params.append(f"%{normalized_invoice_type}%")

        query = (
            "SELECT DISTINCT "
            "    CAST(invoiceType AS NVARCHAR(64)) AS InvoiceType, "
            "    CAST(DocumentType AS NVARCHAR(256)) AS DocumentName, "
            "    CONVERT(varchar(10), issueDate, 23) AS IssueDate, "
            "    CAST(aa AS NVARCHAR(64)) AS aa, "
            "    CAST(InvoiceId AS NVARCHAR(128)) AS InvoiceId, "
            "    CAST(CustAFM AS NVARCHAR(32)) AS CustAFM "
            f"FROM {table} "
            "WHERE " + " AND ".join(where_parts) + " "
            "ORDER BY IssueDate DESC, aa DESC"
        )

        logger.info("Provider search SQL table=%s params=%s", table, params)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        invoices: list[ProviderInvoiceRow] = []

        for row in rows:
            invoices.append(
                ProviderInvoiceRow(
                    InvoiceType=str(row.InvoiceType),
                    DocumentName=str(row.DocumentName),
                    IssueDate=str(row.IssueDate),
                    aa=str(row.aa),
                    InvoiceId=str(row.InvoiceId),
                    CustAFM=str(row.CustAFM),
                )
            )

        return invoices

    def _table_exists(self, cursor, table_name: str) -> bool:
        """
        Ελέγχει αν υπάρχει table/view στη βάση.
        """

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = ?
            """,
            table_name
        )

        return int(cursor.fetchone()[0]) > 0

    def _is_valid_yyyymmdd(self, value: str) -> bool:
        """
        Ελέγχει αν η ημερομηνία είναι σε μορφή YYYYMMDD.
        """

        return bool(re.fullmatch(r"\d{8}", value or ""))

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