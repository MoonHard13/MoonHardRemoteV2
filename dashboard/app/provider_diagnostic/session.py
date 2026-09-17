import re
import time
from threading import RLock
from uuid import uuid4

from app.provider_diagnostic.models import VerifiedProviderCredentials


class ProviderContextSession:
    """Κρατά προσωρινή επιλογή ΑΦΜ και κλειδί δεμένα με πελάτη και βάση."""

    KEY_TTL_SECONDS = 600
    REQUEST_TIMEOUT_SECONDS = 80

    def __init__(self):
        self._lock = RLock()
        self.generation = 0
        self.clear()

    @staticmethod
    def scope(context):
        return (context.client_code, context.bo_connection_id, context.database_server, context.database_name)

    def clear(self):
        with self._lock:
            self.generation += 1
            self._scope = None
            self._pending = None
            self._credentials = None
            self._expires = 0
            self.companies = []
            self.issuer_vat = ""
            self.invalid_afm_count = 0
            self.sql_verified = False
            self.message = "Ανακτήστε εταιρείες με F5 και επιλέξτε ΑΦΜ εκδότη."

    @property
    def pending(self):
        with self._lock:
            return self._pending is not None

    def request(self, context, issuer_vat=""):
        with self._lock:
            if not context.client_connected or context.bo_connection_id is None:
                raise ValueError("Απαιτείται συνδεδεμένος Client και επιλεγμένο BOConnection.")
            if issuer_vat and issuer_vat not in {row["issuer_vat"] for row in self.companies}:
                raise ValueError("Επιλέξτε ΑΦΜ από τις εταιρείες της βάσης.")
            scope = self.scope(context)
            if scope != self._scope:
                self.clear()
            self._scope = scope
            self.generation += 1
            self._credentials = None
            self.issuer_vat = issuer_vat
            if not issuer_vat:
                self.companies = []
                self.sql_verified = False
            request_id = str(uuid4())
            self._pending = (request_id, scope, issuer_vat, time.monotonic())
            self.message = "Ανάκτηση στοιχείων από τον Client…"
            return {"type": "provider_diagnostic_context", "request_id": request_id,
                    "client_code": context.client_code, "bo_connection_id": context.bo_connection_id,
                    "issuer_vat": issuer_vat}

    def cancel(self, message="Ακυρώθηκε η ανάκτηση στοιχείων."):
        with self._lock:
            self.generation += 1
            self._pending = None
            self._credentials = None
            self.message = message

    def expire_pending(self):
        with self._lock:
            if self._pending and time.monotonic() - self._pending[3] > self.REQUEST_TIMEOUT_SECONDS:
                self.cancel("Δεν ελήφθη απάντηση. Ελέγξτε σύνδεση και έκδοση Client/server.")
                return True
            return False

    def accept(self, payload, context):
        with self._lock:
            pending = self._pending
            if (not pending or payload.get("request_id") != pending[0]
                    or self.scope(context) != pending[1]
                    or payload.get("client_code") != context.client_code
                    or payload.get("bo_connection_id") != context.bo_connection_id):
                return False
            self._pending = None
            self._credentials = None
            try:
                rows = payload.get("companies", [])
                if not isinstance(rows, list) or len(rows) > 2000:
                    raise ValueError
                companies = []
                seen = set()
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError
                    issuer = row.get("issuer_vat")
                    if not isinstance(issuer, str) or not re.fullmatch(r"EL[0-9]{9}", issuer) or issuer in seen:
                        raise ValueError
                    seen.add(issuer)
                    name = row.get("company_name", "")
                    if not isinstance(name, str) or len(name) > 500:
                        raise ValueError
                    companies.append({"issuer_vat": issuer, "company_name": name})
                self.companies = companies
                self.sql_verified = payload.get("sql_verified") is True
                self.invalid_afm_count = payload.get("invalid_afm_count", 0)
                if type(self.invalid_afm_count) is not int or not 0 <= self.invalid_afm_count <= 2000:
                    raise ValueError
                if payload.get("success") is not True:
                    # Τα ελεγχόμενα Client errors δεν περιέχουν raw ODBC ή Provider responses.
                    self.message = "Απέτυχε η ανάκτηση. Ελέγξτε σύνδεση, ΑΦΜ και subscriptionKey του BOConnection."
                    return True
                if pending[2]:
                    if payload.get("issuer_vat") != pending[2] or pending[2] not in seen:
                        raise ValueError
                    self._credentials = VerifiedProviderCredentials(context.client_code,
                        context.bo_connection_id, pending[2], payload.get("api_key", ""),
                        "Client: BOConnections.subscriptionKey / dbo.TblSnCompany.CompanyAFM")
                    self._expires = time.monotonic() + self.KEY_TTL_SECONDS
                    self.message = "Έτοιμος για χειροκίνητο Provider έλεγχο."
                else:
                    self.issuer_vat = ""
                    self.message = "Επιλέξτε ΑΦΜ εκδότη." if companies else "Δεν βρέθηκαν εταιρείες με ΑΦΜ 9 ψηφίων."
                return True
            except (ValueError, TypeError, AttributeError):
                self._credentials = None
                self.message = "Η απάντηση δεν περιέχει έγκυρα στοιχεία του επιλεγμένου context."
                return True

    def resolve(self, context):
        with self._lock:
            if self._credentials is not None and time.monotonic() >= self._expires:
                self.message = "Το προσωρινό κλειδί έληξε. Επιλέξτε ξανά εταιρεία ή πατήστε F5."
            if (self.scope(context) != self._scope or not context.client_connected
                    or time.monotonic() >= self._expires):
                self._credentials = None
            if context.issuer_vat and context.issuer_vat != self.issuer_vat:
                return None
            return self._credentials
