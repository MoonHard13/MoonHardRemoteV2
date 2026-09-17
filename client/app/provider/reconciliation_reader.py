"""Περιορισμένη ανάγνωση παραστατικών πώλησης, χωρίς εκτέλεση procedures ή εγγραφές SQL."""

import logging
import re
from contextlib import closing
from datetime import datetime, timedelta

import pyodbc

from app.provider.diagnostic_context import ProviderDiagnosticContextReader


logger = logging.getLogger(__name__)


class ReconciliationReader:
    TABLES = ("VSnVSalesPayWay", "TblSnSNoteHdr", "TblSnMyDATA_Response",
              "TblSnMyDATA_ResponseSuccess", "TblSnCompany")
    PAGE_SIZE = 200

    def __init__(self, settings, provider):
        self.settings, self.provider = settings, provider

    @staticmethod
    def validate(payload):
        issuer = payload.get("issuer_vat")
        if not isinstance(issuer, str) or not re.fullmatch(r"EL[0-9]{9}", issuer):
            raise ValueError
        dates = []
        for name in ("date_from", "date_to"):
            value = payload.get(name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{8}", value):
                raise ValueError
            dates.append(datetime.strptime(value, "%Y%m%d"))
        if dates[0] > dates[1] or dates[1].year == 9999:
            raise ValueError
        if payload.get("source") not in ("pos", "sales"):
            raise ValueError
        before = payload.get("before_oid")
        if before is not None and (type(before) is not int or not 1 <= before <= 2147483647):
            raise ValueError
        if type(payload.get("bo_connection_id")) is not int or not 1 <= payload["bo_connection_id"] <= 2147483647:
            raise ValueError
        return dates[0], dates[1] + timedelta(days=1), issuer, before

    @classmethod
    def metadata(cls, cursor):
        schema = {}
        for table in cls.TABLES:
            cursor.execute("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(?)", ["dbo." + table])
            schema[table] = {str(row[0]).lower() for row in cursor.fetchall()}
        return schema

    @staticmethod
    def company_filter(columns, single_company, issuer):
        if single_company:
            return "1 = 1", []
        if "companyoid" not in columns:
            raise ValueError("Δεν τεκμηριώνεται η εταιρεία των παραστατικών.")
        return ("EXISTS (SELECT 1 FROM dbo.TblSnCompany AS c WHERE c.CompanyOID = base.CompanyOID "
                "AND UPPER(LTRIM(RTRIM(c.CompanyAFM))) IN (?, ?, ?))",
                [issuer[2:], issuer, "GR" + issuer[2:]])

    @classmethod
    def build_query(cls, schema, source, start, end, issuer, single_company, before):
        table = "VSnVSalesPayWay" if source == "pos" else "TblSnSNoteHdr"
        columns = schema[table]
        required = ({"salespaywayoid", "salespwposhdr", "salespwnotecode", "salespwnoterow", "salespwnoteno", "salespwdate"}
            if source == "pos" else {"snotehdroid", "snotehdrprndate", "snotehdrsr", "snotehdrno"})
        if not required <= columns:
            raise ValueError("Δεν υποστηρίζεται το διαθέσιμο σχήμα παραστατικών.")
        company, company_params = cls.company_filter(columns, single_company, issuer)
        params = [cls.PAGE_SIZE + 1, start, end, *company_params]
        if source == "pos":
            seek = "AND doc.page_oid < ?" if before else ""
            base_sql = f"""SELECT MAX(base.SalesPayWayOID) AS page_oid,
                base.SalesPWPosHdr AS link_oid, base.SalesPWNoteRow AS series,
                CAST(base.SalesPWNoteNo AS nvarchar(128)) AS number,
                MAX(base.SalesPWDate) AS dateIssued, CAST(NULL AS decimal(19,4)) AS totalAmount,
                CAST(NULL AS decimal(19,4)) AS totalVatAmount, N'' AS counterPartyVAT
                FROM dbo.VSnVSalesPayWay AS base
                WHERE {company}
                GROUP BY base.SalesPWPosHdr, base.SalesPWNoteCode, base.SalesPWNoteRow,
                    base.SalesPWNoteNo"""
            params = [cls.PAGE_SIZE + 1, *company_params, start, end]
            link = "MyDATA_ResponseSalesTransPosHdr"
        else:
            seek = "AND base.SNoteHdrOID < ?" if before else ""
            def optional(name, fallback):
                return "base.[" + name + "]" if name.lower() in columns else fallback
            base_sql = f"""SELECT TOP (?) base.SNoteHdrOID AS page_oid, base.SNoteHdrOID AS link_oid,
                base.SNoteHdrSr AS series, CAST(base.SNoteHdrNo AS nvarchar(128)) AS number,
                base.SNoteHdrPrnDate AS dateIssued,
                {optional('SNoteHdrVPayTotal', 'NULL')} AS totalAmount,
                {optional('SNoteHdrVFpaTotal', 'NULL')} AS totalVatAmount,
                {optional('SNoteHdrCustAFM', "N''")} AS counterPartyVAT
                FROM dbo.TblSnSNoteHdr AS base WHERE base.SNoteHdrPrnDate >= ? AND base.SNoteHdrPrnDate < ?
                    AND {company} {seek} ORDER BY base.SNoteHdrOID DESC"""
            link = "SNoteHdrOID"
        if before:
            params.append(before)
        md, success = schema["TblSnMyDATA_Response"], schema["TblSnMyDATA_ResponseSuccess"]
        success_available = {"mydata_responseoid", "mydata_responsesuccessoid", "mydata_responsesuccessinvoicemark"} <= success
        relation = f"md.[{link}] = doc.link_oid" if link.lower() in md else ""
        if not relation and source == "sales" and success_available and "snotehdroid" in success:
            relation = ("EXISTS (SELECT 1 FROM dbo.TblSnMyDATA_ResponseSuccess AS ref "
                "WHERE ref.MyDATA_ResponseOID = md.MyDATA_ResponseOID AND ref.SNoteHdrOID = doc.link_oid)")
        warnings = []
        if relation and "mydata_responseoid" in md:
            def field(name):
                return f"NULLIF(LTRIM(RTRIM(CAST(md.[{name}] AS nvarchar(500)))), N'')" if name.lower() in md else "CAST(NULL AS nvarchar(500))"
            mark = field("MyDATA_ResponseInvoiceMARK")
            success_sql = ""
            if success_available:
                success_sql = """OUTER APPLY (SELECT TOP (1) s.MyDATA_ResponseSuccessInvoiceMARK AS mark
                    FROM dbo.TblSnMyDATA_ResponseSuccess AS s WHERE s.MyDATA_ResponseOID = md.MyDATA_ResponseOID
                    AND NULLIF(LTRIM(RTRIM(s.MyDATA_ResponseSuccessInvoiceMARK)), N'') IS NOT NULL
                    ORDER BY s.MyDATA_ResponseSuccessOID DESC) AS suc"""
                mark = f"COALESCE({mark}, NULLIF(LTRIM(RTRIM(suc.mark)), N''))"
            for name, doc_field in (("MyDATA_ResponseInvoiceSeries", "series"), ("MyDATA_ResponseInvoiceNumber", "number")):
                if name.lower() in md:
                    relation += f" AND ({field(name)} IS NULL OR {field(name)} = LTRIM(RTRIM(doc.{doc_field})))"
            response_sql = f"""OUTER APPLY (SELECT TOP (1) {mark} AS mark,
                {field('MyDATA_ResponseInvoiceUID')} AS uid,
                {field('MyDATA_ResponseInvoiceType')} AS invoiceType,
                {field('MyDATA_ResponseInvoiceDate')} AS invoice_date,
                {field('MyDATA_ResponseStatusCode')} AS response_status
                FROM dbo.TblSnMyDATA_Response AS md {success_sql} WHERE {relation}
                ORDER BY CASE WHEN {mark} IS NULL THEN 1 ELSE 0 END, md.MyDATA_ResponseOID DESC) AS response"""
        else:
            # Το σκέτο NULL έχει τύπο int και δεν μετατρέπεται σε datetime2 από TRY_CONVERT.
            empty_text = "CAST(NULL AS nvarchar(500))"
            response_sql = (f"OUTER APPLY (SELECT {empty_text} AS mark, {empty_text} AS uid, "
                f"{empty_text} AS invoiceType, {empty_text} AS invoice_date, {empty_text} AS response_status) AS response")
            warnings.append(f"{source}: δεν τεκμηριώνεται σύνδεση παραστατικού με MyDATA_Response.")
        if source == "pos":
            warnings.append("POS: δεν έχει τεκμηριωθεί πηγή συνολικής αξίας/ΦΠΑ· τα ποσά δεν συγκρίνονται.")
        effective_date = "COALESCE(TRY_CONVERT(datetime2, response.invoice_date), doc.dateIssued)" if source == "pos" else "doc.dateIssued"
        verified = "CASE WHEN TRY_CONVERT(datetime2, response.invoice_date) IS NOT NULL THEN 1 ELSE 0 END" if source == "pos" else "1"
        if source == "pos":
            warnings.append("POS χωρίς MyDATA InvoiceDate: διαθέσιμη μόνο ημερομηνία πληρωμής· η έκδοση δεν επιβεβαιώνεται.")
        outer_top = "TOP (?) " if source == "pos" else ""
        outer_where = f"WHERE {effective_date} >= ? AND {effective_date} < ? {seek}" if source == "pos" else ""
        query = f"""SELECT {outer_top}doc.page_oid, N'{source}:' + CAST(doc.page_oid AS nvarchar(20)) AS document_id,
            doc.series, doc.number, CONVERT(varchar(19), {effective_date}, 126) AS dateIssued,
            {verified} AS issue_date_verified,
            doc.totalAmount, doc.totalVatAmount, doc.counterPartyVAT,
            response.mark, response.uid, response.invoiceType, response.response_status
            FROM ({base_sql}) AS doc {response_sql} {outer_where} ORDER BY doc.page_oid DESC"""
        return query, params, warnings

    @staticmethod
    def sql_error_details(exc):
        """Εξάγει μόνο κωδικούς· ποτέ μήνυμα SQL, credentials ή περιεχόμενο εγγραφών."""
        args = getattr(exc, "args", ())
        state = args[0] if args and isinstance(args[0], str) and re.fullmatch(r"[A-Z0-9]{5}", args[0]) else "-"
        reasons = {102: "syntax", 195: "unsupported_function", 207: "invalid_column",
            208: "missing_object", 229: "select_permission", 245: "conversion",
            468: "collation", 529: "unsupported_conversion", 8115: "overflow", 8180: "statement_preparation"}
        codes = []
        for arg in args:
            if isinstance(arg, str):
                for value in re.findall(r"\(([0-9]{1,6})\)", arg[:10000]):
                    code = int(value)
                    if code in reasons and code not in codes:
                        codes.append(code)
        native = codes[0] if codes else "-"
        reason = reasons.get(native, "parameter_count" if state == "07002" else "unknown")
        return state, native, reason

    def read(self, payload):
        stage, source = "validation", "unknown"
        try:
            start, end, issuer, before = self.validate(payload)
            source = payload["source"]
            stage = "settings"
            settings = self.settings.read_appsettings_production()
            matches = [r for r in settings.get("bo_connections", []) if str(r.get("ID")) == str(payload["bo_connection_id"])]
            if len(matches) != 1 or not matches[0].get("DatabaseConnection"):
                raise ValueError
            stage = "connection"
            odbc = self.provider._to_odbc_connection_string(matches[0]["DatabaseConnection"])
            with closing(pyodbc.connect(odbc, timeout=15)) as connection:
                connection.timeout = 30
                with closing(connection.cursor()) as cursor:
                    stage = "metadata"
                    schema = self.metadata(cursor)
                    if "companyafm" not in schema["TblSnCompany"]:
                        raise ValueError
                    stage = "companies_query"
                    cursor.execute("SELECT CompanyAFM FROM dbo.TblSnCompany")
                    stage = "companies_fetch"
                    companies = [ProviderDiagnosticContextReader.normalize_vat(r[0]) for r in cursor.fetchmany(2001)]
                    if not companies or len(companies) > 2000 or issuer not in companies:
                        raise ValueError
                    source = payload["source"]
                    table = "VSnVSalesPayWay" if source == "pos" else "TblSnSNoteHdr"
                    warnings = ["Οι πηγές ERP καλύπτουν POS και SNoteHdr· λοιπές ροές δεν έχουν επιβεβαιωθεί."]
                    if not schema[table]:
                        return self.result([], False, None, warnings + [f"{source}: η πηγή δεν είναι διαθέσιμη."])
                    single_company = set(companies) == {issuer}
                    if not single_company and "companyoid" not in schema["TblSnCompany"]:
                        raise ValueError
                    stage = "query_build"
                    query, params, notes = self.build_query(schema, source, start, end, issuer, single_company, before)
                    stage = "erp_query"
                    cursor.execute(query, params)
                    stage = "erp_fetch"
                    names = [c[0] for c in cursor.description]
                    rows = cursor.fetchmany(self.PAGE_SIZE + 1)
                    records = []
                    stage = "row_projection"
                    for row in rows[:self.PAGE_SIZE]:
                        record = dict(zip(names, row))
                        record["page_oid"] = int(record["page_oid"])
                        record["issue_date_verified"] = record["issue_date_verified"] == 1
                        for key in names:
                            if key not in ("page_oid", "issue_date_verified"):
                                record[key] = None if record[key] is None else str(record[key])[:500]
                        record["issuer_vat"], record["source"] = issuer, source
                        records.append(record)
                    more = len(rows) > self.PAGE_SIZE
            logger.info("Ανάγνωση ERP για σύγκριση. source=%s records=%s has_more=%s", source, len(records), more)
            return self.result(records, more, records[-1]["page_oid"] if more else None, warnings + notes)
        except Exception as exc:
            state, native, reason = self.sql_error_details(exc)
            logger.warning("Αποτυχία ανάγνωσης ERP για σύγκριση. exception_type=%s source=%s stage=%s "
                "sqlstate=%s native_code=%s reason=%s", type(exc).__name__, source, stage, state, native, reason)
            return {"success": False, "error": "Δεν ήταν δυνατή η ανάγνωση ERP. Ελέγξτε σχήμα, σύνδεση εταιρείας και δικαιώματα SELECT.",
                    "records": [], "has_more": False, "next_before_oid": None, "coverage_complete": False, "warnings": []}

    @staticmethod
    def result(records, more, before, warnings):
        return {"success": True, "records": records, "has_more": more, "next_before_oid": before,
                "coverage_complete": False, "warnings": warnings}
