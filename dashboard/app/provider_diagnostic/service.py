from collections.abc import Callable
from datetime import date
from threading import Event

from app.provider_diagnostic.api_client import ProviderAPIClient
from app.provider_diagnostic.context import CustomerContextAdapter
from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError
from app.provider_diagnostic.models import DiagnosticContext, VerifiedProviderCredentials
from app.provider_diagnostic.documents import DocumentLoader
from app.provider_diagnostic.erp_data import ERPLoader
from app.provider_diagnostic.reconciliation import ReconciliationEngine


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
        # Ο έλεγχος χρησιμοποιεί πραγματική ανάγνωση μίας σελίδας, χωρίς health polling.
        page = ProviderAPIClient(credentials, diagnostics or self.diagnostics).get_documents_page(today, today, cancel=cancel)
        return {"records": len(page.documents), "scope": "Πρώτη σελίδα σημερινών εξερχόμενων παραστατικών"}

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
