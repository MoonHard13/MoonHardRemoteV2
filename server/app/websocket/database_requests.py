import asyncio
import logging
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class PendingDatabaseRequest:
    """Κρατά μόνο τα στοιχεία που απαιτούνται για ασφαλή δρομολόγηση απάντησης."""

    dashboard: object
    client_code: str
    bo_connection_id: int
    action: str
    timer: asyncio.TimerHandle | None = None


class DatabaseRequestRouter:
    """Ελέγχει και δρομολογεί αποκλειστικά τις προκαθορισμένες database actions."""

    REQUEST_TYPE = "database_action"
    RESULT_TYPE = "database_action_result"
    ACTION_TIMEOUTS: ClassVar[dict[str, int]] = {
        "test_connection": 30,
        "sales_trans_info": 60,
        "mydata_info": 60,
        "clean_mydata": 600,
        "history": 1800,
        "shrink": 3600,
        "rebuild": 7200,
    }
    PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        "test_connection": frozenset(),
        "sales_trans_info": frozenset(),
        "mydata_info": frozenset(),
        "clean_mydata": frozenset({"start_date", "end_date"}),
        "history": frozenset({"history_date"}),
        "shrink": frozenset(),
        "rebuild": frozenset(),
    }

    def __init__(self, manager) -> None:
        """Αρχικοποιεί το προσωρινό state χωρίς αποθήκευση περιεχομένου βάσης."""

        self.manager = manager
        self.pending: dict[str, PendingDatabaseRequest] = {}

    @staticmethod
    def error_payload(
        request_id: str,
        client_code: str,
        bo_connection_id: int,
        action: str,
        error: str,
    ) -> dict:
        """Δημιουργεί ομοιόμορφη αποτυχία database action."""

        return {
            "type": DatabaseRequestRouter.RESULT_TYPE,
            "request_id": request_id,
            "client_code": client_code,
            "bo_connection_id": bo_connection_id,
            "action": action,
            "success": False,
            "error": error,
            "database_name": "",
            "elapsed_ms": None,
        }

    async def request(self, dashboard, data: dict) -> None:
        """Επικυρώνει το αίτημα και προωθεί μόνο allowlisted πεδία στον σωστό client."""

        request_id = data.get("request_id", "")
        client_code = data.get("client_code", "")
        bo_connection_id = data.get("bo_connection_id", 1)
        action = data.get("action", "")
        parameters = data.get("parameters", {})

        try:
            UUID(request_id)
            if (
                not isinstance(client_code, str)
                or not client_code
                or len(client_code) > 128
            ):
                raise ValueError
            if (
                type(bo_connection_id) is not int
                or not 1 <= bo_connection_id <= 2147483647
            ):
                raise ValueError
            if not isinstance(action, str) or action not in self.ACTION_TIMEOUTS:
                raise ValueError
            if not isinstance(parameters, dict):
                raise TypeError
            if set(parameters) != self.PARAMETER_KEYS[action]:
                raise ValueError
            if any(
                not isinstance(value, str) or len(value) > 16
                for value in parameters.values()
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    str(request_id),
                    str(client_code),
                    bo_connection_id if type(bo_connection_id) is int else 1,
                    str(action),
                    "Invalid database action request.",
                ),
            )
            return

        if (
            request_id in self.pending
            or sum(pending.dashboard is dashboard for pending in self.pending.values())
            >= 2
        ):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    bo_connection_id,
                    action,
                    "There are already pending database actions. Wait for completion.",
                ),
            )
            return

        pending = PendingDatabaseRequest(
            dashboard=dashboard,
            client_code=client_code,
            bo_connection_id=bo_connection_id,
            action=action,
        )
        self.pending[request_id] = pending
        action_timeout = self.ACTION_TIMEOUTS[action]
        pending.timer = asyncio.get_running_loop().call_later(
            action_timeout + 30,
            lambda: asyncio.create_task(self._expire(request_id)),
        )

        forwarded = {
            "type": self.REQUEST_TYPE,
            "request_id": request_id,
            "client_code": client_code,
            "bo_connection_id": bo_connection_id,
            "action": action,
            "parameters": parameters,
            "timeout": action_timeout,
        }

        try:
            sent = await self.manager.send_to_client(client_code, forwarded)
        except Exception:  # noqa: BLE001 - Η μεταφορά μπορεί να αποτύχει με διαφορετικό transport exception.
            sent = False

        if not sent:
            self._pop(request_id)
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    bo_connection_id,
                    action,
                    "Client is not connected.",
                ),
            )

    async def result(self, client_code: str, data: dict) -> None:
        """Παραδίδει το αποτέλεσμα μόνο στο dashboard που δημιούργησε το αίτημα."""

        request_id = data.get("request_id")
        if not isinstance(request_id, str):
            return

        pending = self.pending.get(request_id)
        if not pending:
            return
        if pending.client_code != client_code:
            return
        if data.get("type") != self.RESULT_TYPE:
            return
        if data.get("bo_connection_id") != pending.bo_connection_id:
            return
        if data.get("action") != pending.action:
            return

        self._pop(request_id)
        await self.manager.send_to_dashboard(
            pending.dashboard,
            {**data, "client_code": client_code},
        )

    async def _expire(self, request_id: str) -> None:
        """Ολοκληρώνει με αποτυχία αίτημα που ξεπέρασε το επιτρεπόμενο όριο."""

        pending = self._pop(request_id)
        if not pending:
            return

        logger.warning(
            "Database action timed out. client_code=%s action=%s",
            pending.client_code,
            pending.action,
        )
        await self.manager.send_to_dashboard(
            pending.dashboard,
            self.error_payload(
                request_id,
                pending.client_code,
                pending.bo_connection_id,
                pending.action,
                "Database action timed out.",
            ),
        )

    def _pop(self, request_id: str) -> PendingDatabaseRequest | None:
        """Αφαιρεί το pending request και ακυρώνει το χρονόμετρό του."""

        pending = self.pending.pop(request_id, None)
        if pending and pending.timer:
            pending.timer.cancel()
        return pending

    def discard_dashboard(self, dashboard) -> None:
        """Αφαιρεί τα pending requests dashboard που αποσυνδέθηκε."""

        for request_id, pending in list(self.pending.items()):
            if pending.dashboard is dashboard:
                self._pop(request_id)
