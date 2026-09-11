import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class PendingBackupRequest:
    """Κρατά τα ελάχιστα στοιχεία για ιδιωτική δρομολόγηση backup απάντησης."""

    dashboard: object
    client_code: str
    bo_connection_id: int
    operation: str
    timer: asyncio.TimerHandle | None = None


class BackupRequestRouter:
    """Ελέγχει backup requests και δεν επιτρέπει SQL ή executable injection."""

    REQUEST_TYPE = "backup_request"
    RESULT_TYPE = "backup_result"
    PROGRESS_TYPE = "backup_progress"
    REQUIRED_CAPABILITY = "database_backup_v1"
    OPERATION_TIMEOUTS: ClassVar[dict[str, int]] = {
        "run": 14500,
        "list": 60,
        "save_schedule": 60,
        "delete_schedule": 60,
        "run_schedule": 14500,
        "retry_pending": 14500,
        "list_cloud_remotes": 60,
    }
    PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        "run": frozenset({"settings"}),
        "list": frozenset(),
        "save_schedule": frozenset({"schedule"}),
        "delete_schedule": frozenset({"schedule_id"}),
        "run_schedule": frozenset({"schedule_id"}),
        "retry_pending": frozenset(),
        "list_cloud_remotes": frozenset(),
    }
    SETTINGS_KEYS = frozenset(
        {
            "destination_type",
            "destination_path",
            "staging_path",
            "cloud_remote",
            "retention_mode",
            "retention_count",
            "compression",
            "copy_only",
        }
    )
    SCHEDULE_KEYS = frozenset(
        {
            "schedule_id",
            "name",
            "bo_connection_id",
            "frequency",
            "time",
            "weekday",
            "day_of_month",
            "enabled",
            "settings",
        }
    )

    def __init__(self, manager) -> None:
        self.manager = manager
        self.pending: dict[str, PendingBackupRequest] = {}

    async def request(self, dashboard, data: dict[str, Any]) -> None:
        """Επικυρώνει και προωθεί μόνο allowlisted backup payloads."""

        request_id = data.get("request_id", "")
        client_code = data.get("client_code", "")
        bo_connection_id = data.get("bo_connection_id", 1)
        operation = data.get("operation", "")
        parameters = data.get("parameters", {})
        try:
            UUID(str(request_id))
            if not isinstance(client_code, str) or not 1 <= len(client_code) <= 128:
                raise ValueError
            if (
                type(bo_connection_id) is not int
                or not 1 <= bo_connection_id <= 2147483647
            ):
                raise ValueError
            if operation not in self.OPERATION_TIMEOUTS:
                raise ValueError
            if not isinstance(parameters, dict):
                raise TypeError
            if set(parameters) != self.PARAMETER_KEYS[operation]:
                raise ValueError
            self._validate_parameters(operation, parameters)
        except (ValueError, TypeError, AttributeError):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    str(request_id),
                    str(client_code),
                    bo_connection_id if type(bo_connection_id) is int else 1,
                    str(operation),
                    "Invalid backup request.",
                ),
            )
            return

        supports = getattr(self.manager, "client_supports", None)
        if callable(supports) and not supports(client_code, self.REQUIRED_CAPABILITY):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    bo_connection_id,
                    operation,
                    "The connected client does not support database backups. "
                    "Update and restart the MoonHard Remote Client.",
                ),
            )
            return

        if (
            request_id in self.pending
            or sum(item.dashboard is dashboard for item in self.pending.values()) >= 3
        ):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    bo_connection_id,
                    operation,
                    "There are already pending backup requests. Wait for completion.",
                ),
            )
            return

        pending = PendingBackupRequest(
            dashboard=dashboard,
            client_code=client_code,
            bo_connection_id=bo_connection_id,
            operation=operation,
        )
        self.pending[request_id] = pending
        timeout = self.OPERATION_TIMEOUTS[operation]
        pending.timer = asyncio.get_running_loop().call_later(
            timeout + 30,
            lambda: asyncio.create_task(self._expire(request_id)),
        )
        forwarded = {
            "type": self.REQUEST_TYPE,
            "request_id": request_id,
            "client_code": client_code,
            "bo_connection_id": bo_connection_id,
            "operation": operation,
            "parameters": parameters,
            "timeout": timeout,
        }
        try:
            sent = await self.manager.send_to_client(client_code, forwarded)
        except Exception:  # noqa: BLE001 - Το transport μπορεί να επιστρέψει διαφορετικό exception.
            sent = False
        if not sent:
            self._pop(request_id)
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    bo_connection_id,
                    operation,
                    "Client is not connected.",
                ),
            )

    async def result(self, client_code: str, data: dict[str, Any]) -> None:
        """Παραδίδει result μόνο στο dashboard που δημιούργησε το request."""

        pending = self._matching_pending(client_code, data, self.RESULT_TYPE)
        if not pending:
            return
        request_id = str(data["request_id"])
        self._pop(request_id)
        await self.manager.send_to_dashboard(
            pending.dashboard,
            {**data, "client_code": client_code},
        )

    async def progress(self, client_code: str, data: dict[str, Any]) -> None:
        """Προωθεί συσχετισμένη και περιορισμένη live πρόοδο backup."""

        pending = self._matching_pending(client_code, data, self.PROGRESS_TYPE)
        if not pending:
            return
        message = data.get("message")
        stage = data.get("stage")
        percent = data.get("percent")
        if not isinstance(message, str) or not 1 <= len(message) <= 1000:
            return
        if not isinstance(stage, str) or not re.fullmatch(r"[a-z_]{1,32}", stage):
            return
        if percent is not None and (
            isinstance(percent, bool)
            or not isinstance(percent, (int, float))
            or not 0 <= float(percent) <= 100
        ):
            return
        payload = {
            "type": self.PROGRESS_TYPE,
            "request_id": data["request_id"],
            "client_code": client_code,
            "bo_connection_id": pending.bo_connection_id,
            "operation": pending.operation,
            "stage": stage,
            "message": message,
        }
        if percent is not None:
            payload["percent"] = float(percent)
        await self.manager.send_to_dashboard(pending.dashboard, payload)

    def discard_dashboard(self, dashboard) -> None:
        """Καθαρίζει timers όταν αποσυνδέεται dashboard."""

        for request_id in [
            key for key, item in self.pending.items() if item.dashboard is dashboard
        ]:
            self._pop(request_id)

    async def _expire(self, request_id: str) -> None:
        pending = self._pop(request_id)
        if not pending:
            return
        await self.manager.send_to_dashboard(
            pending.dashboard,
            self.error_payload(
                request_id,
                pending.client_code,
                pending.bo_connection_id,
                pending.operation,
                "Backup request timed out.",
            ),
        )

    def _matching_pending(
        self, client_code: str, data: dict[str, Any], expected_type: str
    ) -> PendingBackupRequest | None:
        request_id = data.get("request_id")
        if not isinstance(request_id, str):
            return None
        pending = self.pending.get(request_id)
        if not pending or pending.client_code != client_code:
            return None
        if data.get("type") != expected_type:
            return None
        if data.get("bo_connection_id") != pending.bo_connection_id:
            return None
        if data.get("operation") != pending.operation:
            return None
        return pending

    def _pop(self, request_id: str) -> PendingBackupRequest | None:
        pending = self.pending.pop(request_id, None)
        if pending and pending.timer:
            pending.timer.cancel()
        return pending

    @classmethod
    def _validate_parameters(cls, operation: str, parameters: dict[str, Any]) -> None:
        if operation == "run":
            cls._validate_settings(parameters["settings"])
        elif operation == "save_schedule":
            schedule = parameters["schedule"]
            if not isinstance(schedule, dict) or set(schedule) != cls.SCHEDULE_KEYS:
                raise ValueError
            if (
                not isinstance(schedule["schedule_id"], str)
                or len(schedule["schedule_id"]) > 36
            ):
                raise ValueError
            if (
                not isinstance(schedule["name"], str)
                or not 1 <= len(schedule["name"].strip()) <= 80
            ):
                raise ValueError
            if (
                type(schedule["bo_connection_id"]) is not int
                or not 1 <= schedule["bo_connection_id"] <= 2147483647
            ):
                raise ValueError
            if schedule["frequency"] not in {"daily", "weekly", "monthly"}:
                raise ValueError
            if not isinstance(schedule["time"], str) or not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d", schedule["time"]
            ):
                raise ValueError
            if (
                type(schedule["weekday"]) is not int
                or not 0 <= schedule["weekday"] <= 6
            ):
                raise ValueError
            if (
                type(schedule["day_of_month"]) is not int
                or not 1 <= schedule["day_of_month"] <= 31
            ):
                raise ValueError
            if type(schedule["enabled"]) is not bool:
                raise ValueError
            cls._validate_settings(schedule["settings"])
        elif operation in {"delete_schedule", "run_schedule"}:
            UUID(str(parameters["schedule_id"]))

    @classmethod
    def _validate_settings(cls, settings: Any) -> None:
        if not isinstance(settings, dict) or set(settings) != cls.SETTINGS_KEYS:
            raise ValueError
        if settings["destination_type"] not in {"local", "unc", "cloud"}:
            raise ValueError
        for key, maximum in (
            ("destination_path", 1024),
            ("staging_path", 1024),
            ("cloud_remote", 512),
        ):
            if not isinstance(settings[key], str) or len(settings[key]) > maximum:
                raise ValueError
        if settings["retention_mode"] not in {"replace", "keep_all", "keep_last"}:
            raise ValueError
        if (
            type(settings["retention_count"]) is not int
            or not 1 <= settings["retention_count"] <= 365
        ):
            raise ValueError
        if (
            type(settings["compression"]) is not bool
            or type(settings["copy_only"]) is not bool
        ):
            raise ValueError

    @staticmethod
    def error_payload(
        request_id: str,
        client_code: str,
        bo_connection_id: int,
        operation: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "type": BackupRequestRouter.RESULT_TYPE,
            "request_id": request_id,
            "client_code": client_code,
            "bo_connection_id": bo_connection_id,
            "operation": operation,
            "success": False,
            "status": "failed",
            "message": "Backup operation failed.",
            "error": error,
        }
