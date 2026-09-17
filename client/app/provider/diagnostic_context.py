import logging
import re
from contextlib import closing
from urllib.parse import urlsplit

import pyodbc


logger = logging.getLogger(__name__)


class ProviderConfigurationError(ValueError):
    """Μεταφέρει μόνο γνωστό κωδικό, χωρίς πραγματικά στοιχεία ρυθμίσεων."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ProviderDiagnosticContextReader:
    """Ανακτά εταιρείες από τη σωστή βάση και το τοπικό subscriptionKey."""

    MAX_COMPANIES = 2000
    IMPACT_PROVIDER_CONNECTION_ID = 1
    PROVIDER_HOSTS = frozenset(("einvoice.impact.gr", "einvoiceapi.impact.gr", "einvoiceapiuat.impact.gr"))

    @classmethod
    def _normalize_base_url(cls, value):
        if not isinstance(value, str):
            raise ProviderConfigurationError("provider_url_invalid")
        value = value.strip()
        if any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise ProviderConfigurationError("provider_url_invalid")
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError:
            raise ProviderConfigurationError("provider_url_invalid") from None
        if (parts.scheme != "https" or parts.hostname not in cls.PROVIDER_HOSTS
                or parts.username is not None or parts.password is not None
                or port not in (None, 443) or parts.query or parts.fragment
                or parts.path.rstrip("/") not in ("", "/api", "/api/invoice")):
            raise ProviderConfigurationError("provider_url_invalid")
        return f"https://{parts.hostname}"

    def _provider_base_url(self, data, selected):
        """Χρησιμοποιεί ρητή αντιστοίχιση ή την επιβεβαιωμένη σύνδεση IMPACT ID 1."""
        providers = [row for row in data.get("provider_connections", []) if isinstance(row, dict)]
        if not providers:
            raise ProviderConfigurationError("provider_connections_missing")
        references = {str(value) for key, value in selected.items()
                      if str(key).lower() == "providerconnectionid" and value is not None}
        if len(references) > 1:
            raise ProviderConfigurationError("provider_reference_ambiguous")
        if not references:
            references = {str(self.IMPACT_PROVIDER_CONNECTION_ID)}
        # Επιλέγουμε πρώτα τη σύνδεση· εγγραφές άλλων παρόχων δεν ελέγχονται ως IMPACT.
        providers = [row for row in providers if str(row.get("ID")) in references]
        if len(providers) != 1:
            raise ProviderConfigurationError("provider_reference_missing")
        return self._normalize_base_url(providers[0].get("BaseURL"))

    def __init__(self, appsettings_reader, provider_service):
        self._settings = appsettings_reader
        self._provider = provider_service

    @staticmethod
    def normalize_vat(value):
        """Διατηρεί αρχικά μηδενικά και προσθέτει το ελληνικό πρόθεμα χώρας."""
        value = str(value or "").strip().upper()
        if value.startswith(("EL", "GR")):
            value = value[2:]
        return "EL" + value if re.fullmatch(r"[0-9]{9}", value) else ""

    def read(self, bo_id, issuer_vat=""):
        try:
            if type(bo_id) is not int or not 1 <= bo_id <= 2147483647:
                raise ValueError
            if not isinstance(issuer_vat, str) or (issuer_vat and not re.fullmatch(r"EL[0-9]{9}", issuer_vat)):
                raise ValueError
            data = self._settings.read_appsettings_production()
            matches = [row for row in data.get("bo_connections", [])
                       if isinstance(row, dict) and str(row.get("ID")) == str(bo_id)]
            if len(matches) != 1 or not matches[0].get("DatabaseConnection"):
                return self.failure("Το επιλεγμένο BOConnection δεν είναι διαθέσιμο ή δεν είναι μοναδικό.", "bo_connection_missing")
            selected = matches[0]
            try:
                base_url = self._provider_base_url(data, selected)
            except ProviderConfigurationError as exc:
                logger.warning("Αποτυχία αντιστοίχισης Provider. error_code=%s", exc.code)
                return self.failure("Ελέγξτε BaseURL και αντιστοίχιση ProviderConnectionID του επιλεγμένου BOConnection.", exc.code)
            companies, invalid = self._companies(selected["DatabaseConnection"])
            result = {"success": True, "companies": companies, "invalid_afm_count": invalid,
                      "issuer_vat": "", "sql_verified": True, "provider_base_url": base_url}
            if not companies:
                return {**result, "success": False,
                        "error_code": "issuer_vat_missing",
                        "error": "Δεν βρέθηκε ΑΦΜ 9 ψηφίων στο TblSnCompany.CompanyAFM."}
            if issuer_vat:
                if issuer_vat not in {row["issuer_vat"] for row in companies}:
                    return self.failure("Το επιλεγμένο ΑΦΜ δεν υπάρχει στην επιλεγμένη βάση.", "issuer_vat_unknown")
                key = selected.get("subscriptionKey")
                if (not isinstance(key, str) or not key.strip() or "*" in key or len(key) > 4096
                        or any(ord(c) < 32 or ord(c) == 127 for c in key)):
                    return {**result, "success": False,
                            "error_code": "subscription_key_invalid",
                            "error": "Το subscriptionKey του επιλεγμένου BOConnection δεν είναι διαθέσιμο ή έγκυρο."}
                result.update(issuer_vat=issuer_vat, api_key=key)
            logger.info("Ανάκτηση Provider context ολοκληρώθηκε. companies=%s", len(companies))
            return result
        except Exception as exc:
            # Οι ODBC εξαιρέσεις ενδέχεται να περιλαμβάνουν ευαίσθητα στοιχεία σύνδεσης.
            logger.warning("Αποτυχία ανάκτησης Provider context. exception_type=%s", type(exc).__name__)
            return self.failure("Απέτυχε η ανάγνωση εταιρειών. Ελέγξτε βάση, TblSnCompany και δικαιώματα SELECT.")

    @staticmethod
    def failure(message, code="context_read_failed"):
        return {"success": False, "error": message, "error_code": code,
                "companies": [], "issuer_vat": "", "sql_verified": False}

    def _companies(self, connection_string):
        odbc = self._provider._to_odbc_connection_string(connection_string)
        # Το closing κλείνει και τον cursor και τη σύνδεση, ακόμη και σε αποτυχία.
        with closing(pyodbc.connect(odbc, timeout=15)) as connection:
            connection.timeout = 30
            with closing(connection.cursor()) as cursor:
                cursor.execute("SELECT name FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.TblSnCompany')")
                columns = {str(row[0]).lower() for row in cursor.fetchall()}
                if "companyafm" not in columns:
                    raise ValueError("Δεν υπάρχει το CompanyAFM.")
                name = "COALESCE(CAST([CompanyName] AS nvarchar(200)), N'')" if "companyname" in columns else "N''"
                code = "COALESCE(CAST([CompanyCode] AS nvarchar(50)), N'')" if "companycode" in columns else "N''"
                cursor.execute(f"SELECT TOP ({self.MAX_COMPANIES + 1}) [CompanyAFM], {name}, {code} FROM dbo.TblSnCompany")
                rows = cursor.fetchall()
        if len(rows) > self.MAX_COMPANIES:
            raise ValueError("Υπέρβαση ορίου εταιρειών· δεν χρησιμοποιούμε μερική λίστα.")
        grouped, invalid = {}, 0
        for afm, name, code in rows:
            issuer = self.normalize_vat(afm)
            if not issuer:
                invalid += 1
                continue
            labels = grouped.setdefault(issuer, set())
            label = str(name or "").strip() or str(code or "").strip()
            if label:
                labels.add(label)
        return [{"issuer_vat": issuer, "company_name": " / ".join(sorted(labels))[:500]}
                for issuer, labels in sorted(grouped.items())], invalid
