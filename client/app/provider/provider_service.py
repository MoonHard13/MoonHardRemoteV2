import logging
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    def send_invoices(
        self,
        api_url_template: str,
        invoice_ids: list[str],
        timeout: int = 60,
        max_workers: int = 6
    ) -> dict[str, Any]:
        """
        Στέλνει παραστατικά προς Provider API όπως το MUPT.
        Η αποστολή γίνεται από τον client υπολογιστή.
        Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
        """

        clean_url = api_url_template.strip()
        clean_invoice_ids = [str(invoice_id).strip() for invoice_id in invoice_ids if str(invoice_id).strip()]

        if not clean_url:
            return {
                "success": False,
                "error": "Provider API URL is empty.",
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "results": []
            }

        if "invoiceid" not in clean_url.lower():
            return {
                "success": False,
                "error": "Provider API URL must contain invoiceid placeholder.",
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "results": []
            }

        if not clean_invoice_ids:
            return {
                "success": False,
                "error": "No invoice IDs selected.",
                "total": 0,
                "success_count": 0,
                "fail_count": 0,
                "results": []
            }

        start_time = time.perf_counter()
        results: list[dict[str, Any]] = []

        logger.info(
            "Starting provider invoice send. total=%s max_workers=%s",
            len(clean_invoice_ids),
            max_workers
        )

        worker_count = max(1, min(max_workers, len(clean_invoice_ids)))

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(
                    self._send_single_invoice,
                    clean_url,
                    invoice_id,
                    timeout
                ): invoice_id
                for invoice_id in clean_invoice_ids
            }

            for future in as_completed(future_map):
                invoice_id = future_map[future]

                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.exception("Provider invoice send crashed. invoice_id=%s", invoice_id)

                    results.append(
                        {
                            "invoice_id": invoice_id,
                            "success": False,
                            "status_code": None,
                            "elapsed_ms": None,
                            "url": self._build_invoice_url(clean_url, invoice_id),
                            "response_text": "",
                            "error": str(exc)
                        }
                    )

        success_count = sum(1 for item in results if item.get("success"))
        fail_count = len(results) - success_count
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "success": fail_count == 0,
            "error": None if fail_count == 0 else f"{fail_count} invoice(s) failed.",
            "total": len(results),
            "success_count": success_count,
            "fail_count": fail_count,
            "elapsed_ms": elapsed_ms,
            "results": results
        }

    def _send_single_invoice(
        self,
        api_url_template: str,
        invoice_id: str,
        timeout: int
    ) -> dict[str, Any]:
        """
        Στέλνει ένα παραστατικό στο Provider API.
        """

        final_url = self._build_invoice_url(api_url_template, invoice_id)
        start_time = time.perf_counter()

        logger.info("Sending provider invoice. invoice_id=%s url=%s", invoice_id, final_url)

        request = urllib.request.Request(
            final_url,
            data=b"",
            method="POST",
            headers={
                "User-Agent": "MoonHardRemoteV2-ProviderSender/1.0",
                "Accept": "application/json, text/plain, */*"
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status_code = response.getcode()
                raw_body = response.read()
                response_text = raw_body.decode("utf-8", errors="replace")

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            return {
                "invoice_id": invoice_id,
                "success": 200 <= int(status_code) < 300,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "url": final_url,
                "response_text": response_text[:4000],
                "error": None
            }

        except urllib.error.HTTPError as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            try:
                response_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                response_text = ""

            return {
                "invoice_id": invoice_id,
                "success": False,
                "status_code": exc.code,
                "elapsed_ms": elapsed_ms,
                "url": final_url,
                "response_text": response_text[:4000],
                "error": str(exc)
            }

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            return {
                "invoice_id": invoice_id,
                "success": False,
                "status_code": None,
                "elapsed_ms": elapsed_ms,
                "url": final_url,
                "response_text": "",
                "error": str(exc)
            }

    def _build_invoice_url(self, api_url_template: str, invoice_id: str) -> str:
        """
        Αντικαθιστά το invoiceid placeholder με το πραγματικό InvoiceId.
        """

        return re.sub(
            "invoiceid",
            str(invoice_id),
            api_url_template,
            flags=re.IGNORECASE
        )

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
    
    def get_mydata_errors(
        self,
        connection_string: str,
        start_yyyymmdd: str,
        end_yyyymmdd: str,
        limit: int = 300,
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Φέρνει MyDATA / Provider errors από TblSnMyDATA_Response.
        Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
        """

        start = start_yyyymmdd.strip()
        end = end_yyyymmdd.strip()
        safe_limit = max(1, min(int(limit), 1000))

        if not self._is_valid_yyyymmdd(start):
            return {
                "success": False,
                "error": "Invalid start_date. Expected YYYYMMDD.",
                "errors": [],
                "count": 0
            }

        if not self._is_valid_yyyymmdd(end):
            return {
                "success": False,
                "error": "Invalid end_date. Expected YYYYMMDD.",
                "errors": [],
                "count": 0
            }

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                if not self._table_exists(cursor, "TblSnMyDATA_Response"):
                    raise RuntimeError("Table TblSnMyDATA_Response was not found.")

                table_columns = self._get_table_columns(cursor, "TblSnMyDATA_Response")

                rows = self._fetch_mydata_error_rows(
                    cursor=cursor,
                    table_columns=table_columns,
                    start_yyyymmdd=start,
                    end_yyyymmdd=end,
                    limit=safe_limit
                )

            return {
                "success": True,
                "error": None,
                "errors": rows,
                "count": len(rows)
            }

        except Exception as exc:
            logger.exception("Provider MyDATA errors fetch failed.")

            return {
                "success": False,
                "error": str(exc),
                "errors": [],
                "count": 0
            }

    def delete_mydata_for_documents(
        self,
        connection_string: str,
        documents: list[dict],
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Διαγράφει MyDATA responses για επιλεγμένα παραστατικά με MUPT λογική.
        Χρησιμοποιεί VSnVSalesPayWay, SalesPWNoteCode και SalesPWNoteNo.
        Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
        """

        clean_documents: list[dict[str, str]] = []

        for document in documents:
            note_code = str(document.get("note_code", "")).strip()
            note_no = str(document.get("note_no", "")).strip()

            if note_code and note_no:
                clean_documents.append(
                    {
                        "note_code": note_code,
                        "note_no": note_no
                    }
                )

        if not clean_documents:
            return {
                "success": False,
                "error": "No valid documents selected.",
                "documents": [],
                "deleted_success_rows": 0,
                "deleted_response_rows": 0
            }

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                if not self._table_exists(cursor, "TblSnMyDATA_Response"):
                    raise RuntimeError("Table TblSnMyDATA_Response was not found.")

                if not self._table_exists(cursor, "VSnVSalesPayWay"):
                    raise RuntimeError("View VSnVSalesPayWay was not found.")

                response_columns = self._get_table_columns(
                    cursor,
                    "TblSnMyDATA_Response"
                )

                if "mydata_responsesalestransposhdr" not in response_columns:
                    raise RuntimeError(
                        "Column MyDATA_ResponseSalesTransPosHdr was not found in TblSnMyDATA_Response."
                    )

                total_deleted_success_rows = 0
                total_deleted_response_rows = 0

                for document in clean_documents:
                    note_code = document["note_code"]
                    note_no = document["note_no"]

                    delete_result = self._delete_mydata_single_document(
                        cursor=cursor,
                        note_code=note_code,
                        note_no=note_no
                    )

                    total_deleted_success_rows += delete_result["deleted_success_rows"]
                    total_deleted_response_rows += delete_result["deleted_response_rows"]

                connection.commit()

            return {
                "success": True,
                "error": None,
                "documents": clean_documents,
                "deleted_success_rows": total_deleted_success_rows,
                "deleted_response_rows": total_deleted_response_rows
            }

        except Exception as exc:
            logger.exception("Provider MyDATA delete failed.")

            return {
                "success": False,
                "error": str(exc),
                "documents": clean_documents,
                "deleted_success_rows": 0,
                "deleted_response_rows": 0
            }


    def _delete_mydata_single_document(
        self,
        cursor,
        note_code: str,
        note_no: str
    ) -> dict[str, int]:
        """
        Διαγράφει MyDATA για ένα παραστατικό με ίδια λογική όπως το MUPT.
        """

        where_sql = """
            INNER JOIN VSnVSalesPayWay spw
                ON md.MyDATA_ResponseSalesTransPosHdr = spw.SalesPWPosHdr
            WHERE CAST(spw.SalesPWNoteCode AS NVARCHAR(128)) = ?
              AND CAST(spw.SalesPWNoteNo AS NVARCHAR(128)) = ?
        """

        params = [note_code, note_no]

        return self._delete_mydata_with_children(
            cursor=cursor,
            where_sql=where_sql,
            params=params
        )


    def _delete_mydata_with_children(
        self,
        cursor,
        where_sql: str,
        params: list
    ) -> dict[str, int]:
        """
        Διαγράφει πρώτα child rows από TblSnMyDATA_ResponseSuccess
        και μετά parent rows από TblSnMyDATA_Response.
        """

        deleted_success_rows = 0
        deleted_response_rows = 0

        if self._table_exists(cursor, "TblSnMyDATA_ResponseSuccess"):
            success_columns = self._get_table_columns(
                cursor,
                "TblSnMyDATA_ResponseSuccess"
            )

            if "mydata_responsesuccesssalestransposhdr" in success_columns:
                cursor.execute(
                    f"""
                    DELETE suc
                    FROM TblSnMyDATA_ResponseSuccess suc
                    INNER JOIN TblSnMyDATA_Response md
                        ON md.MyDATA_ResponseSalesTransPosHdr =
                           suc.MyDATA_ResponseSuccessSalesTransPosHdr
                    {where_sql}
                    """,
                    params
                )

                deleted_success_rows = cursor.rowcount if cursor.rowcount != -1 else 0

        cursor.execute(
            f"""
            DELETE md
            FROM TblSnMyDATA_Response md
            {where_sql}
            """,
            params
        )

        deleted_response_rows = cursor.rowcount if cursor.rowcount != -1 else 0

        return {
            "deleted_success_rows": deleted_success_rows,
            "deleted_response_rows": deleted_response_rows
        }

    def get_invoice_payways(
        self,
        connection_string: str,
        invoice_id: str,
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Φέρνει τρόπους πληρωμής για συγκεκριμένο παραστατικό.
        Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
        """

        clean_invoice_id = str(invoice_id).strip()

        if not clean_invoice_id:
            return {
                "success": False,
                "error": "InvoiceId is empty.",
                "payways": [],
                "count": 0
            }

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                if self._table_exists(cursor, "vsnvsalespayway"):
                    payways = self._fetch_payways_from_view(
                        cursor=cursor,
                        invoice_id=clean_invoice_id
                    )
                elif self._table_exists(cursor, "tblsnsalespayway"):
                    payways = self._fetch_payways_from_table(
                        cursor=cursor,
                        invoice_id=clean_invoice_id
                    )
                else:
                    raise RuntimeError(
                        "Δεν βρέθηκε ούτε το vsnvsalespayway ούτε το tblsnsalespayway."
                    )

            return {
                "success": True,
                "error": None,
                "payways": payways,
                "count": len(payways)
            }

        except Exception as exc:
            logger.exception("Provider payways fetch failed.")

            return {
                "success": False,
                "error": str(exc),
                "payways": [],
                "count": 0
            }


    def _fetch_payways_from_view(
        self,
        cursor,
        invoice_id: str
    ) -> list[dict[str, Any]]:
        """
        Φέρνει τρόπους πληρωμής από το view vsnvsalespayway.
        Η λογική ακολουθεί το original MUPT:
        WHERE spw.SalesPWPosHdr = InvoiceId
        """

        required_tables = [
            "TblSnPayWay",
            "TblSnSalesMan"
        ]

        for table_name in required_tables:
            if not self._table_exists(cursor, table_name):
                raise RuntimeError(f"Table {table_name} was not found.")

        query = """
            SELECT
                CAST(pw.PayWayDescr AS NVARCHAR(255)) AS PayWayDescr,
                CAST(spw.SalesPWValue AS NVARCHAR(64)) AS SalesPWValue,
                CAST(sm.SalesManLName AS NVARCHAR(255)) AS SalesManLName,
                CAST(spw.SalesPayWayOID AS NVARCHAR(128)) AS SalesPayWayOID
            FROM vsnvsalespayway spw
            INNER JOIN TblSnPayWay pw
                ON spw.PayWayOID = pw.PayWayOID
            INNER JOIN TblSnSalesMan sm
                ON spw.SalesPWSalesMan = sm.SalesManOID
            WHERE CAST(spw.SalesPWPosHdr AS NVARCHAR(128)) = ?
        """

        logger.info("Provider payways SQL invoice_id=%s", invoice_id)

        cursor.execute(query, invoice_id)

        return self._rows_to_dicts(cursor)


    def _fetch_payways_from_table(
        self,
        cursor,
        invoice_id: str
    ) -> list[dict[str, Any]]:
        """
        Fallback: φέρνει τρόπους πληρωμής από tblsnsalespayway.
        Χρησιμοποιεί SalesPWPosHdr όταν υπάρχει.
        """

        table_columns = self._get_table_columns(cursor, "tblsnsalespayway")

        invoice_column = self._find_first_existing_column(
            table_columns=table_columns,
            possible_columns=[
                "SalesPWPosHdr",
                "salespwposhdr",
                "SalesInPWPosHdr",
                "salesinpwposhdr"
            ]
        )

        if not invoice_column:
            raise RuntimeError(
                "Could not find SalesPWPosHdr column in tblsnsalespayway."
            )

        preferred_columns = [
            "SalesPayWayOID",
            "SalesPWPosHdr",
            "PayWayOID",
            "SalesPWValue",
            "SalesPWSalesMan",
            "SalesPWDate"
        ]

        selected_columns = [
            column
            for column in preferred_columns
            if column.lower() in table_columns
        ]

        if not selected_columns:
            selected_columns = list(table_columns)[:10]

        select_parts = [
            f"CAST([{column}] AS NVARCHAR(MAX)) AS [{column}]"
            for column in selected_columns
        ]

        query = (
            "SELECT "
            + ", ".join(select_parts)
            + " FROM [tblsnsalespayway] "
            + f"WHERE CAST([{invoice_column}] AS NVARCHAR(128)) = ?"
        )

        logger.info("Provider payways fallback SQL invoice_id=%s", invoice_id)

        cursor.execute(query, invoice_id)

        return self._rows_to_dicts(cursor)


    def _find_first_existing_column(
        self,
        table_columns: set[str],
        possible_columns: list[str]
    ) -> str:
        """
        Βρίσκει την πρώτη στήλη που υπάρχει στον πίνακα.
        """

        for column in possible_columns:
            if column.lower() in table_columns:
                return column

        return ""


    def _rows_to_dicts(self, cursor) -> list[dict[str, Any]]:
        """
        Μετατρέπει pyodbc rows σε list από dictionaries.
        """

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        result_rows: list[dict[str, Any]] = []

        for row in rows:
            item: dict[str, Any] = {}

            for index, column in enumerate(columns):
                value = row[index]
                item[column] = "" if value is None else str(value)

            result_rows.append(item)

        return result_rows
            
    def _fetch_mydata_error_rows(
        self,
        cursor,
        table_columns: set[str],
        start_yyyymmdd: str,
        end_yyyymmdd: str,
        limit: int
    ) -> list[dict[str, Any]]:
        """
        Διαβάζει error rows από TblSnMyDATA_Response με δυναμικό έλεγχο στηλών.
        """

        preferred_columns = [
            "MyDATA_ResponseOID",
            "MyDATA_ResponseDate",
            "MyDATA_ResponseNoteType",
            "MyDATA_ResponseNumber",
            "MyDATA_ResponseStatusCode",
            "MyDATA_ResponseErrorMessage",
            "MyDATA_ResponseRequest",
            "MyDATA_ResponseResponse"
        ]

        selected_columns = [
            column
            for column in preferred_columns
            if column.lower() in table_columns
        ]

        if not selected_columns:
            selected_columns = list(table_columns)[:8]

        select_parts = [
            f"CAST([{column}] AS NVARCHAR(MAX)) AS [{column}]"
            for column in selected_columns
        ]

        where_parts: list[str] = []
        params: list[Any] = []

        if "mydata_responsedate" in table_columns:
            where_parts.append(
                "CONVERT(date, [MyDATA_ResponseDate]) BETWEEN CONVERT(date, ?, 112) AND CONVERT(date, ?, 112)"
            )
            params.extend([start_yyyymmdd, end_yyyymmdd])

        error_conditions: list[str] = []

        if "mydata_responseerrormessage" in table_columns:
            error_conditions.append(
                "NULLIF(LTRIM(RTRIM(CAST([MyDATA_ResponseErrorMessage] AS NVARCHAR(MAX)))), '') IS NOT NULL"
            )

        if "mydata_responsestatuscode" in table_columns:
            error_conditions.append(
                "ISNULL(CAST([MyDATA_ResponseStatusCode] AS NVARCHAR(128)), '') <> 'Success'"
            )

        if error_conditions:
            where_parts.append("(" + " OR ".join(error_conditions) + ")")

        where_sql = ""

        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        order_sql = ""

        if "mydata_responsedate" in table_columns:
            order_sql = "ORDER BY [MyDATA_ResponseDate] DESC"

        query = (
            f"SELECT TOP {limit} "
            + ", ".join(select_parts)
            + " FROM [TblSnMyDATA_Response] "
            + where_sql
            + " "
            + order_sql
        )

        logger.info("Provider errors SQL params=%s", params)

        cursor.execute(query, params)

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        result_rows: list[dict[str, Any]] = []

        for row in rows:
            item: dict[str, Any] = {}

            for index, column in enumerate(columns):
                value = row[index]
                item[column] = "" if value is None else str(value)

            result_rows.append(item)

        return result_rows
    
    def _get_table_columns(self, cursor, table_name: str) -> set[str]:
        """
        Επιστρέφει τις στήλες ενός table/view σε lowercase μορφή.
        """

        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            """,
            table_name
        )

        return {
            str(row[0]).lower()
            for row in cursor.fetchall()
        }
        
    def delete_payway(
        self,
        connection_string: str,
        sales_payway_oid: str,
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Διαγράφει τρόπο πληρωμής από tblsnsalespayway και tblsnsalespaywayhist.
        Δεν αποθηκεύει δεδομένα στον server ή στη Supabase.
        """

        clean_oid = str(sales_payway_oid).strip()

        if not clean_oid:
            return {
                "success": False,
                "error": "SalesPayWayOID is empty.",
                "sales_payway_oid": clean_oid,
                "deleted_main_rows": 0,
                "deleted_history_rows": 0
            }

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                deleted_history_rows = 0
                deleted_main_rows = 0

                if self._table_exists(cursor, "tblsnsalespaywayhist"):
                    history_columns = self._get_table_columns(cursor, "tblsnsalespaywayhist")

                    if "salespaywayoid" in history_columns:
                        cursor.execute(
                            """
                            DELETE FROM tblsnsalespaywayhist
                            WHERE CAST(SalesPayWayOID AS NVARCHAR(128)) = ?
                            """,
                            clean_oid
                        )

                        deleted_history_rows = cursor.rowcount if cursor.rowcount != -1 else 0

                if self._table_exists(cursor, "tblsnsalespayway"):
                    main_columns = self._get_table_columns(cursor, "tblsnsalespayway")

                    if "salespaywayoid" not in main_columns:
                        raise RuntimeError("Column SalesPayWayOID was not found in tblsnsalespayway.")

                    cursor.execute(
                        """
                        DELETE FROM tblsnsalespayway
                        WHERE CAST(SalesPayWayOID AS NVARCHAR(128)) = ?
                        """,
                        clean_oid
                    )

                    deleted_main_rows = cursor.rowcount if cursor.rowcount != -1 else 0

                else:
                    raise RuntimeError("Table tblsnsalespayway was not found.")

                connection.commit()

            return {
                "success": True,
                "error": None,
                "sales_payway_oid": clean_oid,
                "deleted_main_rows": deleted_main_rows,
                "deleted_history_rows": deleted_history_rows
            }

        except Exception as exc:
            logger.exception("Provider payway delete failed.")

            return {
                "success": False,
                "error": str(exc),
                "sales_payway_oid": clean_oid,
                "deleted_main_rows": 0,
                "deleted_history_rows": 0
            }
            
    def fetch_note_types(
        self,
        connection_string: str,
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        Φέρνει Note Types από tblSNNoteType όπως το MUPT.
        Επιστρέφει τιμές σε μορφή: NoteTypeDescr|NoteTypeOID.
        """

        try:
            odbc_connection_string = self._to_odbc_connection_string(connection_string)

            with pyodbc.connect(odbc_connection_string, timeout=timeout) as connection:
                cursor = connection.cursor()

                if not self._table_exists(cursor, "tblSNNoteType"):
                    raise RuntimeError("Table tblSNNoteType was not found.")

                cursor.execute(
                    """
                    SELECT CONCAT(NoteTypeDescr, '|', NoteTypeOID) AS NoteTypeValue
                    FROM tblSNNoteType
                    WHERE NoteTypeMyDATAIncluded = 1
                    ORDER BY 1
                    """
                )

                note_types = [
                    str(row[0])
                    for row in cursor.fetchall()
                ]

            return {
                "success": True,
                "error": None,
                "note_types": note_types,
                "count": len(note_types)
            }

        except Exception as exc:
            logger.exception("Provider note types fetch failed.")

            return {
                "success": False,
                "error": str(exc),
                "note_types": [],
                "count": 0
            }