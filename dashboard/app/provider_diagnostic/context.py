from collections.abc import Callable
from dataclasses import replace

from app.provider_diagnostic.models import DiagnosticContext, VerifiedProviderCredentials


class CustomerContextAdapter:
    """Επαναχρησιμοποιεί την επιλογή πελάτη/βάσης χωρίς νέο selector ή secrets."""

    def __init__(self, get_client: Callable[[], dict], get_bo: Callable[[], dict],
                 get_bo_id: Callable[[], int], parse_connection: Callable[[str], dict]) -> None:
        self._get_client = get_client
        self._get_bo = get_bo
        self._get_bo_id = get_bo_id
        self._parse_connection = parse_connection

    def snapshot(self) -> DiagnosticContext:
        client, bo = self._get_client(), self._get_bo()
        selected_id = self._get_bo_id()
        # Απορρίπτουμε fallback σε άλλη βάση, ώστε να αποφεύγεται λάθος αντιστοίχιση.
        if str(bo.get("ID", "")) != str(selected_id):
            bo = {}
        parts = self._parse_connection(str(bo.get("DatabaseConnection") or ""))
        return DiagnosticContext(
            client_code=str(client.get("client_code") or ""),
            display_name=str(client.get("display_name") or client.get("pc_name") or "-"),
            bo_connection_id=selected_id if bo else None,
            database_server=str(bo.get("DatabaseServer") or parts.get("server") or ""),
            database_name=str(bo.get("DatabaseName") or parts.get("database") or ""),
            client_connected=bool(client.get("ws_connected", False)),
        )

    @staticmethod
    def bind(context: DiagnosticContext, credentials: VerifiedProviderCredentials) -> DiagnosticContext:
        if (credentials.client_code != context.client_code
                or credentials.bo_connection_id != context.bo_connection_id):
            raise ValueError("Τα στοιχεία Provider δεν αντιστοιχούν στον επιλεγμένο πελάτη/βάση.")
        return replace(context, issuer_vat=credentials.issuer_vat,
                       provider_ready=True, provider_reason="")
