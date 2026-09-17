import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID


logger = logging.getLogger(__name__)


@dataclass
class PendingTransmittedRequest:
    """Προσωρινά στοιχεία δρομολόγησης χωρίς περιεχόμενο παραστατικών."""

    dashboard: object
    client_code: str
    result_type: str
    bo_connection_id: int
    timer: asyncio.TimerHandle | None = None


class TransmittedRequestRouter:
    """Προωθεί απαντήσεις αποκλειστικά στο dashboard που ζήτησε την ανάγνωση."""

    REQUEST_TYPES = ("provider_transmitted_search", "provider_transmitted_types")
    RESULT_TYPES = tuple(f"{name}_result" for name in REQUEST_TYPES)
    TIMEOUT_SECONDS = 75
    ALLOWED_FIELDS = ("type", "request_id", "client_code", "bo_connection_id", "start_date",
                      "end_date", "number", "mark", "document_type", "before_oid", "limit")

    def __init__(self, manager) -> None:
        """Κρατά μόνο προσωρινά αναγνωριστικά συσχέτισης και χρονόμετρα."""
        self.manager = manager
        self.pending: dict[str, PendingTransmittedRequest] = {}

    @staticmethod
    def error_payload(request_id: str, pending: PendingTransmittedRequest, error: str) -> dict:
        """Δημιουργεί κοινή απάντηση αποτυχίας για όλα τα νέα αιτήματα."""
        return {"type": pending.result_type, "request_id": request_id,
                "client_code": pending.client_code, "bo_connection_id": pending.bo_connection_id,
                "success": False, "error": error, "invoices": [], "document_types": [],
                "count": 0, "has_more": False, "next_before_oid": None}

    async def request(self, dashboard, data: dict) -> None:
        """Ελέγχει το περίβλημα και προωθεί μόνο τα αναμενόμενα πεδία φίλτρων."""
        request_id = data.get("request_id", "")
        code = data.get("client_code", "")
        bo_id = data.get("bo_connection_id", 1)
        pending = PendingTransmittedRequest(dashboard, code, f"{data['type']}_result", bo_id)
        try:
            UUID(request_id)
            if not isinstance(code, str) or not code or len(code) > 128:
                raise ValueError
            if type(bo_id) is not int or not 1 <= bo_id <= 2147483647:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            await self.manager.send_to_dashboard(dashboard, self.error_payload(request_id, pending, "Μη έγκυρα στοιχεία αιτήματος."))
            return
        if request_id in self.pending or sum(p.dashboard is dashboard for p in self.pending.values()) >= 4:
            await self.manager.send_to_dashboard(dashboard, self.error_payload(request_id, pending, "Υπάρχουν ήδη εκκρεμή αιτήματα. Περιμένετε την ολοκλήρωσή τους."))
            return
        self.pending[request_id] = pending
        pending.timer = asyncio.get_running_loop().call_later(
            self.TIMEOUT_SECONDS, lambda: asyncio.create_task(self._expire(request_id)))
        forwarded = {key: data[key] for key in self.ALLOWED_FIELDS if key in data}
        try:
            sent = await self.manager.send_to_client(code, forwarded)
        except Exception:
            sent = False
        if not sent:
            self._pop(request_id)
            await self.manager.send_to_dashboard(dashboard, self.error_payload(request_id, pending, "Ο client δεν είναι συνδεδεμένος."))

    def _pop(self, request_id: str) -> PendingTransmittedRequest | None:
        """Αφαιρεί την προσωρινή συσχέτιση και ακυρώνει το χρονόμετρο."""
        pending = self.pending.pop(request_id, None)
        if pending and pending.timer:
            pending.timer.cancel()
        return pending

    async def _expire(self, request_id: str) -> None:
        """Τερματίζει την αναμονή όταν ο client δεν απαντήσει εγκαίρως."""
        pending = self._pop(request_id)
        if pending:
            logger.info("Λήξη αναμονής ανάγνωσης διαβιβασμένων.")
            await self.manager.send_to_dashboard(pending.dashboard, self.error_payload(
                request_id, pending, "Δεν ελήφθη απάντηση εγκαίρως. Ελέγξτε σύνδεση και ενημέρωση server/client."))

    async def result(self, client_code: str, data: dict) -> None:
        """Απορρίπτει ξένες ή καθυστερημένες απαντήσεις χωρίς γενική εκπομπή."""
        request_id = data.get("request_id")
        if not isinstance(request_id, str):
            return
        pending = self.pending.get(request_id)
        if not pending or pending.client_code != client_code or pending.result_type != data.get("type"):
            return
        if data.get("bo_connection_id") != pending.bo_connection_id:
            return
        self._pop(request_id)
        await self.manager.send_to_dashboard(pending.dashboard, {**data, "client_code": client_code})

    def discard_dashboard(self, dashboard) -> None:
        """Καθαρίζει τα αιτήματα όταν κλείσει το συγκεκριμένο dashboard."""
        for request_id, pending in list(self.pending.items()):
            if pending.dashboard is dashboard:
                self._pop(request_id)
