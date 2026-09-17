import re
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class DiagnosticContext:
    """Ασφαλές στιγμιότυπο του ήδη επιλεγμένου πελάτη και BOConnection."""

    client_code: str
    display_name: str
    bo_connection_id: int | None
    database_server: str
    database_name: str
    client_connected: bool
    issuer_vat: str = ""
    provider_ready: bool = False
    provider_reason: str = "Ανακτήστε εταιρείες από τον Client και επιλέξτε ΑΦΜ εκδότη."

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VerifiedProviderCredentials:
    """Προσωρινό subscriptionKey του επιλεγμένου BOConnection και ΑΦΜ εταιρείας."""

    client_code: str
    bo_connection_id: int
    issuer_vat: str
    api_key: str = field(repr=False)
    source: str = field(repr=False)

    def __post_init__(self) -> None:
        # Δεχόμαστε μόνο πραγματικό κλειδί από επιβεβαιωμένη πηγή, ποτέ masked appsettings.
        if (not self.client_code or type(self.bo_connection_id) is not int
                or self.bo_connection_id < 1 or not self.source.strip()
                or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2,20}", self.issuer_vat)
                or not isinstance(self.api_key, str) or not self.api_key.strip()
                or len(self.api_key) > 4096 or "*" in self.api_key
                or any(ord(char) < 32 or ord(char) == 127 for char in self.api_key)):
            raise ValueError("Μη έγκυρα ή ανεπιβεβαίωτα στοιχεία Provider.")


@dataclass(frozen=True)
class APIDiagnostic:
    timestamp: datetime
    endpoint: str
    operation: str
    duration_ms: int
    http_status: int | None
    records: int
    success: bool
    error_category: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


@dataclass(frozen=True)
class DocumentPage:
    """Μία πραγματική σελίδα· η πλήρης φόρτωση ανήκει στη Phase 2."""

    documents: list[dict]
    next_page: str = ""
