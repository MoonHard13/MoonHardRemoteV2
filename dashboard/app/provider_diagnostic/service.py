import logging
from collections.abc import Callable
from datetime import date
from threading import Event

from app.provider_diagnostic.api_client import ProviderAPIClient
from app.provider_diagnostic.context import CustomerContextAdapter
from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError
from app.provider_diagnostic.models import DiagnosticContext, VerifiedProviderCredentials
from app.provider_diagnostic.documents import DocumentFields, DocumentLoader
from app.provider_diagnostic.erp_data import ERPLoader
from app.provider_diagnostic.reconciliation import ReconciliationEngine


logger = logging.getLogger(__name__)


class ProviderDiagnosticService:
    """Συνδέει το customer context με verified credentials και απομονωμένα diagnostics."""

    def __init__(self, context: CustomerContextAdapter,
                 resolve_credentials: Callable[[DiagnosticContext], VerifiedProviderCredentials | None] | None = None) -> None:
        self.context = context
        self.diagnostics = APIDiagnosticStore()
        self._resolver = resolve_credentials

    def snapshot(self) -> DiagnosticContext:
        context = self.context.snapshot()
        if self._resolver:
            try:
                return self.context.bind(context, self.credentials(context))
            except ProviderAPIError:
                pass
        return context

    def credentials(self, context: DiagnosticContext) -> VerifiedProviderCredentials:
        try:
            credentials = self._resolver(context) if self._resolver else None
        except Exception:
            raise ProviderAPIError(ErrorCategory.CONFIGURATION) from None
        if not isinstance(credentials, VerifiedProviderCredentials):
            raise ProviderAPIError(ErrorCategory.CONFIGURATION)
        try:
            self.context.bind(context, credentials)
        except ValueError:
            raise ProviderAPIError(ErrorCategory.CONFIGURATION) from None
        return credentials

    def probe(self, context: DiagnosticContext, cancel: Event,
              diagnostics: APIDiagnosticStore | None = None) -> dict:
        credentials = self.credentials(context)
        today = date.today().strftime("%Y%m%d")
        # Ίδιο ευρύτερο παράθυρο με Documents· τα σημερινά μετρώνται από το dateIssued.
        start, end = DocumentLoader._request_window(today, today)
        page = ProviderAPIClient(credentials, diagnostics or self.diagnostics).get_documents_page(start, end, cancel=cancel)
        if cancel.is_set():
            raise ProviderAPIError(ErrorCategory.CANCELLED)
        issued = [DocumentFields.issued_date(row.get("dateIssued")) for row in page.documents]
        matching = sum(day == today for day in issued)
        invalid = sum(day is None for day in issued)
        message = (f"Πρόσβαση Provider επιβεβαιώθηκε. Πρώτη σελίδα API: {len(page.documents)} εγγραφές · "
            f"Σημερινά στην πρώτη σελίδα: {matching}. Δεν αποτελεί πλήρη λίστα σημερινών παραστατικών.")
        if invalid:
            message += f" Χωρίς έγκυρη ημερομηνία: {invalid}."
        logger.info("Έλεγχος πρόσβασης Provider ολοκληρώθηκε. fetched=%s matching_today=%s invalid_dates=%s",
            len(page.documents), matching, invalid)
        return {"records": len(page.documents), "today_records_on_page": matching,
            "invalid_date_count": invalid, "date_from": today, "date_to": today,
            "api_date_from": start, "api_date_to": end, "list_complete": False,
            "scope": "Έλεγχος πρόσβασης Provider · πρώτη σελίδα ευρύτερου διαστήματος", "message": message}

    def close(self) -> None:
        self.diagnostics.close()

    def documents(self, context, date_from, date_to, cancel, progress=None, diagnostics=None):
        credentials = self.credentials(context)
        client = ProviderAPIClient(credentials, diagnostics or self.diagnostics)
        return DocumentLoader(client).load(date_from, date_to, credentials.issuer_vat, cancel, progress)

    def reconcile(self, context, date_from, date_to, cancel, fetch_erp, progress=None, diagnostics=None):
        """Ανακτά νέα στιγμιότυπα στο ίδιο ΑΦΜ και συγκρίνει χωρίς μεταβολές δεδομένων."""
        provider = self.documents(context, date_from, date_to, cancel, progress, diagnostics)
        erp = ERPLoader.load(fetch_erp, context, date_from, date_to, cancel, progress)
        return ReconciliationEngine.compare(erp, provider, cancel)
