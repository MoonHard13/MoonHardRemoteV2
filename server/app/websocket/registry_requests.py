"""Secure routing for Registry Diagnostic & Management Center."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID


logger = logging.getLogger(__name__)


@dataclass
class PendingRegistryRequest:
    """Minimal state required to route Registry responses privately."""

    dashboard: object
    client_code: str
    operation: str
    timer: asyncio.TimerHandle | None = None


class RegistryRequestRouter:
    """Validates and routes only allowlisted Registry operations."""

    REQUEST_TYPE = "registry_request"
    RESULT_TYPE = "registry_result"
    PROGRESS_TYPE = "registry_progress"
    REQUIRED_CAPABILITY = "registry_v1"

    OPERATION_TIMEOUTS: ClassVar[dict[str, int]] = {
        "context": 30,
        "list_key": 45,
        "get_value": 30,
        "search": 180,
        "create_key": 60,
        "set_value": 60,
        "delete_value": 60,
        "delete_key": 180,
        "snapshot": 300,
        "compare_snapshot": 300,
        "history": 60,
        "restore_backup": 300,
        "diagnostics": 90,
        "profile_list": 60,
        "profile_save": 60,
        "profile_delete": 60,
        "profile_check": 180,
        "profile_apply": 300,
        "export_reg": 300,
        "import_reg_preview": 120,
        "import_reg_apply": 300,
    }

    ALLOWED_PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        "context": frozenset(),
        "list_key": frozenset({"hive", "path", "view"}),
        "get_value": frozenset({"hive", "path", "value_name", "view"}),
        "search": frozenset({"query", "hive", "path", "view", "search_keys", "search_names", "search_data", "max_results", "max_depth"}),
        "create_key": frozenset({"hive", "path", "view"}),
        "set_value": frozenset({"hive", "path", "value_name", "value_type", "value", "view"}),
        "delete_value": frozenset({"hive", "path", "value_name", "view"}),
        "delete_key": frozenset({"hive", "path", "view", "recursive"}),
        "snapshot": frozenset({"hive", "path", "view", "max_entries"}),
        "compare_snapshot": frozenset({"backup_id", "hive", "path", "view"}),
        "history": frozenset({"limit"}),
        "restore_backup": frozenset({"backup_id"}),
        "diagnostics": frozenset(),
        "profile_list": frozenset(),
        "profile_save": frozenset({"name", "entries", "description", "profile_id"}),
        "profile_delete": frozenset({"profile_id"}),
        "profile_check": frozenset({"profile_id"}),
        "profile_apply": frozenset({"profile_id", "mode", "dry_run"}),
        "export_reg": frozenset({"hive", "path", "view", "max_entries"}),
        "import_reg_preview": frozenset({"reg_text", "view"}),
        "import_reg_apply": frozenset({"reg_text", "view"}),
    }

    REQUIRED_PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        "context": frozenset(),
        "list_key": frozenset({"hive"}),
        "get_value": frozenset({"hive", "path", "value_name"}),
        "search": frozenset({"query", "hive"}),
        "create_key": frozenset({"hive", "path"}),
        "set_value": frozenset({"hive", "path", "value_name", "value_type", "value"}),
        "delete_value": frozenset({"hive", "path", "value_name"}),
        "delete_key": frozenset({"hive", "path"}),
        "snapshot": frozenset({"hive"}),
        "compare_snapshot": frozenset({"backup_id"}),
        "history": frozenset(),
        "restore_backup": frozenset({"backup_id"}),
        "diagnostics": frozenset(),
        "profile_list": frozenset(),
        "profile_save": frozenset({"name", "entries"}),
        "profile_delete": frozenset({"profile_id"}),
        "profile_check": frozenset({"profile_id"}),
        "profile_apply": frozenset({"profile_id"}),
        "export_reg": frozenset({"hive", "path"}),
        "import_reg_preview": frozenset({"reg_text"}),
        "import_reg_apply": frozenset({"reg_text"}),
    }

    def __init__(self, manager) -> None:
        self.manager = manager
        self.pending: dict[str, PendingRegistryRequest] = {}

    @staticmethod
    def error_payload(request_id: str, client_code: str, operation: str, error: str) -> dict[str, Any]:
        return {
            "type": RegistryRequestRouter.RESULT_TYPE,
            "request_id": request_id,
            "client_code": client_code,
            "operation": operation,
            "success": False,
            "error": error,
        }

    async def request(self, dashboard, data: dict[str, Any]) -> None:
        """Validate request shape and capability before forwarding."""

        request_id = str(data.get("request_id") or "")
        client_code = str(data.get("client_code") or "")
        operation = str(data.get("operation") or "")
        parameters = data.get("parameters", {})

        try:
            UUID(request_id)
            if not 1 <= len(client_code) <= 128:
                raise ValueError
            if operation not in self.OPERATION_TIMEOUTS:
                raise ValueError
            if not isinstance(parameters, dict):
                raise TypeError
            keys = frozenset(parameters)
            if not self.REQUIRED_PARAMETER_KEYS[operation].issubset(keys):
                raise ValueError
            if not keys.issubset(self.ALLOWED_PARAMETER_KEYS[operation]):
                raise ValueError
            self._validate_parameters(operation, parameters)
        except (ValueError, TypeError, AttributeError):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(request_id, client_code, operation, "Invalid registry request."),
            )
            return

        supports = getattr(self.manager, "client_supports", None)
        if callable(supports) and not supports(client_code, self.REQUIRED_CAPABILITY):
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    operation,
                    "The connected client does not support Registry Center. Update and restart the MoonHard Remote Client.",
                ),
            )
            return

        if request_id in self.pending or sum(item.dashboard is dashboard for item in self.pending.values()) >= 3:
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(
                    request_id,
                    client_code,
                    operation,
                    "There are already pending Registry requests. Wait for completion.",
                ),
            )
            return

        pending = PendingRegistryRequest(dashboard=dashboard, client_code=client_code, operation=operation)
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
            "operation": operation,
            "parameters": parameters,
            "timeout": timeout,
        }

        try:
            sent = await self.manager.send_to_client(client_code, forwarded)
        except Exception:
            sent = False

        if not sent:
            self._pop(request_id)
            await self.manager.send_to_dashboard(
                dashboard,
                self.error_payload(request_id, client_code, operation, "Client is not connected."),
            )

    async def result(self, client_code: str, data: dict[str, Any]) -> None:
        """Deliver result only to the dashboard that created the request."""

        request_id = str(data.get("request_id") or "")
        pending = self.pending.get(request_id)
        if not pending or pending.client_code != client_code:
            return
        if data.get("type") != self.RESULT_TYPE or data.get("operation") != pending.operation:
            return
        self._pop(request_id)
        await self.manager.send_to_dashboard(pending.dashboard, {**data, "client_code": client_code})

    async def progress(self, client_code: str, data: dict[str, Any]) -> None:
        """Forward bounded progress messages without completing the request."""

        request_id = str(data.get("request_id") or "")
        pending = self.pending.get(request_id)
        if not pending or pending.client_code != client_code:
            return
        if data.get("type") != self.PROGRESS_TYPE or data.get("operation") != pending.operation:
            return

        stage = data.get("stage")
        message = data.get("message")
        current = data.get("current")
        total = data.get("total")
        if not isinstance(stage, str) or not re.fullmatch(r"[a-z_]{1,40}", stage):
            return
        if not isinstance(message, str) or not 1 <= len(message) <= 1000:
            return
        if current is not None and (type(current) is not int or current < 0):
            return
        if total is not None and (type(total) is not int or total < 0):
            return

        await self.manager.send_to_dashboard(
            pending.dashboard,
            {
                "type": self.PROGRESS_TYPE,
                "request_id": request_id,
                "client_code": client_code,
                "operation": pending.operation,
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
            },
        )

    async def _expire(self, request_id: str) -> None:
        pending = self._pop(request_id)
        if not pending:
            return
        logger.warning(
            "Registry request timed out. client_code=%s operation=%s",
            pending.client_code,
            pending.operation,
        )
        await self.manager.send_to_dashboard(
            pending.dashboard,
            self.error_payload(
                request_id,
                pending.client_code,
                pending.operation,
                "Registry request timed out.",
            ),
        )

    def _pop(self, request_id: str) -> PendingRegistryRequest | None:
        pending = self.pending.pop(request_id, None)
        if pending and pending.timer:
            pending.timer.cancel()
        return pending

    def discard_dashboard(self, dashboard) -> None:
        for request_id, pending in list(self.pending.items()):
            if pending.dashboard is dashboard:
                self._pop(request_id)

    @staticmethod
    def _validate_parameters(operation: str, parameters: dict[str, Any]) -> None:
        """Apply conservative size/type limits before data reaches the client."""

        hives = {"HKLM", "HKCU", "HKCR", "HKU", "HKCC"}
        views = {"default", "32", "64"}

        hive = parameters.get("hive")
        if hive is not None and str(hive).upper() not in hives:
            raise ValueError

        view = parameters.get("view")
        if view is not None and str(view).lower() not in views:
            raise ValueError

        for key in ("path", "value_name", "query", "name", "description"):
            value = parameters.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 5000):
                raise ValueError

        for key in ("backup_id", "profile_id"):
            value = parameters.get(key)
            if value is not None:
                UUID(str(value))

        reg_text = parameters.get("reg_text")
        if reg_text is not None and (not isinstance(reg_text, str) or len(reg_text) > 2_000_000):
            raise ValueError

        entries = parameters.get("entries")
        if entries is not None and (not isinstance(entries, list) or len(entries) > 1000):
            raise ValueError

        if operation in {"search", "snapshot", "export_reg", "history"}:
            for key in ("max_results", "max_depth", "max_entries", "limit"):
                value = parameters.get(key)
                if value is not None and (type(value) is not int or value < 0 or value > 20_000):
                    raise ValueError

        for key in ("search_keys", "search_names", "search_data", "recursive", "dry_run"):
            value = parameters.get(key)
            if value is not None and type(value) is not bool:
                raise ValueError
