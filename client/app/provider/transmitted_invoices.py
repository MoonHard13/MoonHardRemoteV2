import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pyodbc


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransmittedInvoiceFilters:
    """Επικυρωμένα, ανεξάρτητα φίλτρα αναζήτησης διαβιβασμένων παραστατικών."""

    start_date: datetime | None = None
    end_exclusive: datetime | None = None
    number: str = ""
    mark: str = ""
    document_type: str = ""
    before_oid: int | None = None
    limit: int = 100

    @classmethod
    def from_payload(cls, payload: dict) -> "TransmittedInvoiceFilters":
        """Ελέγχει ημερομηνίες, μήκη και αριθμητικά όρια πριν από τη σύνδεση SQL."""
        def text_value(key: str, maximum: int) -> str:
            value = payload.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"Το πεδίο {key} πρέπει να είναι κείμενο.")
            value = value.strip()
            if len(value) > maximum or any(ord(char) < 32 for char in value):
                raise ValueError(f"Μη έγκυρη τιμή στο πεδίο {key}.")
            return value

        def date_value(key: str) -> datetime | None:
            value = text_value(key, 10)
            if not value:
                return None
            for pattern in ("%Y%m%d", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(value, pattern)
                    if parsed.strftime(pattern) == value:
                        return parsed
                except ValueError:
                    pass
            raise ValueError("Οι ημερομηνίες πρέπει να είναι YYYYMMDD, YYYY-MM-DD ή ΗΗ/ΜΜ/ΕΕΕΕ.")

        start, end = date_value("start_date"), date_value("end_date")
        if start and end and start > end:
            raise ValueError("Η ημερομηνία Από πρέπει να προηγείται της ημερομηνίας Έως.")
        if end and end.year == 9999 and end.month == 12 and end.day == 31:
            raise ValueError("Η ημερομηνία Έως είναι εκτός επιτρεπτών ορίων.")
        document_type = text_value("document_type", 80)
        if document_type and not re.fullmatch(r"note:[1-9][0-9]{0,9}|mydata:[0-9]+(?:\.[0-9]+)*", document_type):
            raise ValueError("Επιλέξτε έγκυρο τύπο παραστατικού από τη λίστα.")
        try:
            raw_limit = payload.get("limit", 100)
            raw_before = payload.get("before_oid")
            if isinstance(raw_limit, bool) or isinstance(raw_before, bool):
                raise ValueError
            limit = int(raw_limit)
            before = int(raw_before) if raw_before is not None else None
            if str(limit) != str(raw_limit) or (before is not None and str(before) != str(raw_before)):
                raise ValueError
            if not 1 <= limit <= 200 or (before is not None and not 1 <= before <= 2147483647):
                raise ValueError
            if document_type.startswith("note:") and int(document_type[5:]) > 2147483647:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Μη έγκυρο όριο αποτελεσμάτων ή αναγνωριστικό σελίδας/τύπου.") from None
        return cls(start, end + timedelta(days=1) if end else None,
                   text_value("number", 128), text_value("mark", 128),
                   document_type, before, limit)


class TransmittedInvoicesService:
    """Ανάγνωση επιτυχών διαβιβάσεων με βάση το επιβεβαιωμένο σχήμα της Sunsoft."""

    MARK_SQL = "COALESCE(NULLIF(LTRIM(RTRIM(md.MyDATA_ResponseInvoiceMARK)), N''), suc.InvoiceMARK)"
    INVOICE_DATE_SQL = "COALESCE(md.MyDATA_ResponseInvoiceDate, doc.SalesPWDate)"
    NUMBER_SQL = """COALESCE(
        NULLIF(LTRIM(RTRIM(md.MyDATA_ResponseInvoiceNumber)), N''),
        CAST(doc.SalesPWNoteNo AS nvarchar(128))
    )"""
    SERIES_SQL = """COALESCE(
        NULLIF(LTRIM(RTRIM(md.MyDATA_ResponseInvoiceSeries)), N''),
        NULLIF(LTRIM(RTRIM(CAST(doc.SalesPWNoteRow AS nvarchar(128)))), N'')
    )"""
    SUCCESS_SQL = """(
        (md.MyDATA_ResponseStatusCode = N'Success'
         AND NULLIF(LTRIM(RTRIM(md.MyDATA_ResponseInvoiceMARK)), N'') IS NOT NULL)
        OR suc.InvoiceMARK IS NOT NULL
    )"""
    SOURCE_SQL = """
        FROM dbo.TblSnMyDATA_Response AS md
        OUTER APPLY (
            SELECT TOP (1)
                NULLIF(LTRIM(RTRIM(s.MyDATA_ResponseSuccessInvoiceMARK)), N'') AS InvoiceMARK
            FROM dbo.TblSnMyDATA_ResponseSuccess AS s
            WHERE s.MyDATA_ResponseOID = md.MyDATA_ResponseOID
              AND NULLIF(LTRIM(RTRIM(s.MyDATA_ResponseSuccessInvoiceMARK)), N'') IS NOT NULL
            ORDER BY s.MyDATA_ResponseSuccessOID DESC
        ) AS suc
    """

    def __init__(self, provider_service) -> None:
        """Χρησιμοποιεί τον υπάρχοντα μηχανισμό τοπικής σύνδεσης ODBC."""
        self.provider_service = provider_service

    @classmethod
    def build_query(cls, filters: TransmittedInvoiceFilters) -> tuple[str, list[Any]]:
        """Κατασκευάζει μόνο SELECT με παραμέτρους και σταθερή σελιδοποίηση κατά OID."""
        where = [cls.SUCCESS_SQL]
        params: list[Any] = [filters.limit + 1]
        for value, predicate in (
            (filters.start_date, cls.INVOICE_DATE_SQL + " >= ?"),
            (filters.end_exclusive, cls.INVOICE_DATE_SQL + " < ?"),
            (filters.number, cls.NUMBER_SQL + " = ?"),
            (filters.mark, cls.MARK_SQL + " = ?"),
            (filters.before_oid, "md.MyDATA_ResponseOID < ?"),
        ):
            if value is not None and value != "":
                where.append(predicate)
                params.append(value)
        if filters.document_type.startswith("note:"):
            where.append("""EXISTS (
                SELECT 1 FROM dbo.VSnVSalesPayWay AS pw
                WHERE pw.SalesPWPosHdr = md.MyDATA_ResponseSalesTransPosHdr
                  AND pw.SalesPWNoteCode = ?
            )""")
            params.append(int(filters.document_type[5:]))
        elif filters.document_type.startswith("mydata:"):
            where.append("md.MyDATA_ResponseInvoiceType = ?")
            params.append(filters.document_type[7:])
        query = f"""
            SELECT TOP (?)
                md.MyDATA_ResponseOID AS ResponseOID,
                CONVERT(varchar(10), {cls.INVOICE_DATE_SQL}, 23) AS InvoiceDate,
                CONVERT(varchar(19), md.MyDATA_ResponseDate, 120) AS ResponseDate,
                CAST({cls.SERIES_SQL} AS nvarchar(128)) AS Series,
                CAST({cls.NUMBER_SQL} AS nvarchar(128)) AS Number,
                COALESCE(CAST(doc.NoteTypeDescr AS nvarchar(256)), md.MyDATA_ResponseInvoiceType) AS DocumentType,
                CAST(md.MyDATA_ResponseInvoiceType AS nvarchar(64)) AS MyDataType,
                CAST({cls.MARK_SQL} AS nvarchar(128)) AS MARK,
                md.MyDATA_ResponseProviderQRCodeLink AS DocumentURL,
                CAST(md.MyDATA_ResponseCancellationMARK AS nvarchar(128)) AS CancellationMARK,
                CONVERT(varchar(19), md.MyDATA_ResponseCancDate, 120) AS CancellationDate
            {cls.SOURCE_SQL}
            OUTER APPLY (
                SELECT TOP (1)
                    pw.SalesPWDate, pw.SalesPWNoteRow, pw.SalesPWNoteNo, t.NoteTypeDescr
                FROM dbo.VSnVSalesPayWay AS pw
                LEFT JOIN dbo.TblSnNoteType AS t ON t.NoteTypeOID = pw.SalesPWNoteCode
                WHERE pw.SalesPWPosHdr = md.MyDATA_ResponseSalesTransPosHdr
                ORDER BY pw.SalesPayWayOID DESC, pw.SalesPWNoteCode,
                         pw.SalesPWNoteNo, pw.SalesPWNoteRow, pw.SalesPWDate
            ) AS doc
            WHERE {" AND ".join(where)}
            ORDER BY md.MyDATA_ResponseOID DESC
        """
        return query, params

    def search(self, connection_string: str, payload: dict) -> dict:
        """Επιστρέφει μία περιορισμένη σελίδα· δεν αποθηκεύει παραστατικά ή συνδέσμους."""
        try:
            filters = TransmittedInvoiceFilters.from_payload(payload)
        except ValueError as exc:
            return self.failure(str(exc))
        try:
            connection_text = self.provider_service._to_odbc_connection_string(connection_string)
            with pyodbc.connect(connection_text, timeout=30) as connection:
                connection.timeout = 30
                cursor = connection.cursor()
                query, params = self.build_query(filters)
                cursor.execute(query, params)
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchmany(filters.limit + 1)
                invoices = []
                page_bytes = 0
                for row in rows[:filters.limit]:
                    invoice = dict(zip(columns, row))
                    invoice["ResponseOID"] = int(invoice["ResponseOID"])
                    for key in columns:
                        if key != "ResponseOID":
                            invoice[key] = "" if invoice[key] is None else str(invoice[key])
                    url = invoice["DocumentURL"].strip()
                    invoice["DocumentURL"] = url if len(url) <= 4096 else ""
                    invoice["URLNote"] = "Το URL υπερβαίνει το επιτρεπτό μήκος." if len(url) > 4096 else ""
                    invoice_bytes = len(json.dumps(invoice, ensure_ascii=False).encode("utf-8"))
                    if invoices and page_bytes + invoice_bytes > 512 * 1024:
                        break
                    invoices.append(invoice)
                    page_bytes += invoice_bytes
            has_more = len(rows) > len(invoices)
            logger.info("Αναζήτηση διαβιβασμένων ολοκληρώθηκε. count=%s has_more=%s", len(invoices), has_more)
            return {"success": True, "error": None, "invoices": invoices,
                    "count": len(invoices), "has_more": has_more,
                    "next_before_oid": invoices[-1]["ResponseOID"] if has_more else None}
        except Exception as exc:
            logger.error("Αποτυχία ανάγνωσης διαβιβασμένων. exception_type=%s", type(exc).__name__)
            return self.failure("Αποτυχία ανάγνωσης διαβιβασμένων. Ελέγξτε BOConnection, σχήμα και δικαιώματα SQL.")

    def get_document_types(self, connection_string: str) -> dict:
        """Επιστρέφει τοπικούς τύπους και κωδικούς MyDATA χωρίς εικασίες για σχέσεις BackOffice."""
        try:
            connection_text = self.provider_service._to_odbc_connection_string(connection_string)
            with pyodbc.connect(connection_text, timeout=30) as connection:
                connection.timeout = 30
                cursor = connection.cursor()
                cursor.execute("""SELECT NoteTypeOID, NoteTypeDescr
                    FROM dbo.TblSnNoteType WHERE NoteTypeMyDATAIncluded = 1 ORDER BY NoteTypeDescr, NoteTypeOID""")
                types = [{"value": f"note:{int(row[0])}", "label": f"POS: {row[1]} [Τύπος {row[0]}]"}
                         for row in cursor.fetchmany(2001)]
                if len(types) > 2000:
                    raise ValueError("Υπερβολικά πολλοί τύποι παραστατικών.")
                cursor.execute("""SELECT DISTINCT TOP (201) MyDATA_ResponseInvoiceType
                    FROM dbo.TblSnMyDATA_Response
                    WHERE MyDATA_ResponseInvoiceType IS NOT NULL
                    ORDER BY MyDATA_ResponseInvoiceType""")
                for row in cursor.fetchmany(201):
                    value = str(row[0]).strip()
                    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value):
                        types.append({"value": f"mydata:{value}", "label": f"MyDATA: {value}"})
            logger.info("Φόρτωση τύπων διαβιβασμένων ολοκληρώθηκε. count=%s", len(types))
            return {"success": True, "error": None, "document_types": types}
        except Exception as exc:
            logger.error("Αποτυχία φόρτωσης τύπων. exception_type=%s", type(exc).__name__)
            return {"success": False, "error": "Αποτυχία φόρτωσης τύπων παραστατικών.", "document_types": []}

    @staticmethod
    def failure(message: str) -> dict:
        """Παρέχει σταθερή δομή αποτυχίας για GUI και CLI."""
        return {"success": False, "error": message, "invoices": [], "count": 0,
                "has_more": False, "next_before_oid": None}
