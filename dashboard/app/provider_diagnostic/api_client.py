import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from threading import Event
from urllib.parse import urlencode

from app.provider_diagnostic.diagnostics import APIDiagnosticStore
from app.provider_diagnostic.errors import ErrorCategory, ProviderAPIError
from app.provider_diagnostic.models import APIDiagnostic, DocumentPage, ProviderEndpoint, VerifiedProviderCredentials


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Δεν επιτρέπει μεταφορά APIKey σε redirect ή διαφορετικό origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProviderAPIClient:
    """Απευθείας HTTPS ανάγνωση documented outgoing documents από το Dashboard."""

    ENDPOINT = "/api/invoice/getdocuments/{IssuerVatNumber}/{PageNumber}/"
    MAX_RESPONSE_BYTES = 8 * 1024 * 1024

    def __init__(self, credentials: VerifiedProviderCredentials, diagnostics: APIDiagnosticStore,
                 timeout: float = 15, max_attempts: int = 3, opener=None) -> None:
        if not 1 <= timeout <= 60 or not 1 <= max_attempts <= 3:
            raise ValueError("Μη έγκυρα όρια επικοινωνίας Provider.")
        self._credentials = credentials
        origin = ProviderEndpoint.documents_origin(credentials.provider_base_url)
        self.base_url = origin + "/api/invoice/getdocuments"
        self.endpoint = origin + self.ENDPOINT
        self.diagnostics = diagnostics
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._opener = opener or urllib.request.build_opener(
            NoRedirectHandler(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        # Δεν κρατάμε δεύτερο αντίγραφο του κλειδιού στον καθολικό redactor.
        # Όλες οι εξαιρέσεις και τα diagnostics χρησιμοποιούν ελεγχόμενα μηνύματα.

    @staticmethod
    def _date(value: str) -> str:
        try:
            if len(value) != 8 or not value.isascii() or not value.isdigit():
                raise ValueError
            datetime.strptime(value, "%Y%m%d")
            return value
        except (ValueError, TypeError):
            raise ProviderAPIError(ErrorCategory.VALIDATION) from None

    def get_documents_page(self, date_from: str, date_to: str, page: int = 1,
                           cancel: Event | None = None) -> DocumentPage:
        start, end = self._date(date_from), self._date(date_to)
        if start > end or type(page) is not int or page < 1:
            raise ProviderAPIError(ErrorCategory.VALIDATION)
        cancel = cancel or Event()
        # Η τεκμηρίωση δείχνει From/dateTo για το συγκεκριμένο paginated endpoint.
        url = f"{self.base_url}/{self._credentials.issuer_vat}/{page}/?" + urlencode(
            {"From": start, "dateTo": end})
        for attempt in range(self.max_attempts):
            if cancel.is_set():
                raise ProviderAPIError(ErrorCategory.CANCELLED)
            request = urllib.request.Request(url, method="GET", headers={
                "APIKey": self._credentials.api_key, "Accept": "application/json",
                "User-Agent": "MoonHardRemoteV2-ProviderDiagnostic/1.0"})
            result, error, retryable = self._attempt(request, cancel,
                f"GetDocumentsPage page={page} From={start} dateTo={end}")
            if error is None:
                return result
            if not retryable or attempt + 1 == self.max_attempts:
                raise error
            if cancel.wait(0.5 * (2 ** attempt)):
                raise ProviderAPIError(ErrorCategory.CANCELLED)
        raise ProviderAPIError(ErrorCategory.CONNECTION)

    def _attempt(self, request, cancel: Event, operation: str) -> tuple[DocumentPage | None, ProviderAPIError | None, bool]:
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc)
        status, records, result, error, retryable = None, 0, None, None, False
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = response.getcode()
                if not 200 <= status < 300:
                    raise urllib.error.HTTPError(request.full_url, status, "", response.headers, None)
                raw = bytearray()
                while True:
                    if cancel.is_set():
                        raise ProviderAPIError(ErrorCategory.CANCELLED, status)
                    if time.perf_counter() - started >= self.timeout:
                        raise ProviderAPIError(ErrorCategory.TIMEOUT, status)
                    chunk = response.read(min(65536, self.MAX_RESPONSE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > self.MAX_RESPONSE_BYTES:
                        raise ProviderAPIError(ErrorCategory.INCOMPLETE_RESPONSE, status)
                expected = response.headers.get("Content-Length")
                if expected is not None and (not expected.isdigit() or int(expected) != len(raw)):
                    raise ProviderAPIError(ErrorCategory.INCOMPLETE_RESPONSE, status)
                try:
                    data = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal)
                except UnicodeDecodeError:
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE, status) from None
                except json.JSONDecodeError:
                    raise ProviderAPIError(ErrorCategory.INVALID_JSON, status) from None
                if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                    raise ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE, status)
                records = len(data)
                result = DocumentPage(data, str(response.headers.get("NextPage") or ""))
        except ProviderAPIError as exc:
            error = exc
        except urllib.error.HTTPError as exc:
            status = exc.code
            category = {401: ErrorCategory.AUTHENTICATION, 403: ErrorCategory.AUTHORIZATION,
                        404: ErrorCategory.NOT_FOUND,
                        400: ErrorCategory.VALIDATION, 422: ErrorCategory.VALIDATION}.get(
                            status, ErrorCategory.HTTP_5XX if status >= 500 else ErrorCategory.HTTP_4XX)
            error = ProviderAPIError(category, status)
            if 300 <= status < 400:
                error = ProviderAPIError(ErrorCategory.UNSUPPORTED, status)
            retryable = status in (500, 502, 503, 504)
            exc.close()
        except (TimeoutError, socket.timeout):
            error, retryable = ProviderAPIError(ErrorCategory.TIMEOUT, status), True
        except ssl.SSLError:
            error = ProviderAPIError(ErrorCategory.CONNECTION, status)
        except urllib.error.URLError as exc:
            timed_out = isinstance(exc.reason, (TimeoutError, socket.timeout))
            error = ProviderAPIError(ErrorCategory.TIMEOUT if timed_out else ErrorCategory.CONNECTION, status)
            retryable = not isinstance(exc.reason, ssl.SSLError)
        except (http.client.IncompleteRead, http.client.RemoteDisconnected):
            error, retryable = ProviderAPIError(ErrorCategory.INCOMPLETE_RESPONSE, status), True
        except (ConnectionError, OSError):
            error, retryable = ProviderAPIError(ErrorCategory.CONNECTION, status), True
        except (ValueError, http.client.HTTPException):
            error = ProviderAPIError(ErrorCategory.MALFORMED_RESPONSE, status)
        if cancel.is_set():
            error, retryable, result = ProviderAPIError(ErrorCategory.CANCELLED, status), False, None
        self.diagnostics.add(APIDiagnostic(
            timestamp, self.endpoint, operation, int((time.perf_counter() - started) * 1000),
            status, records, error is None, error.category.value if error else "",
            error.message if error else ""))
        return result, error, retryable
