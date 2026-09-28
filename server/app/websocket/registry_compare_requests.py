"""Registry router extension for read-only compare captures."""

from __future__ import annotations

from typing import Any, ClassVar

from app.websocket.registry_requests import RegistryRequestRouter


class RegistryCompareRequestRouter(RegistryRequestRouter):
    """Adds the bounded, read-only capture_scope operation used by PC compare."""

    OPERATION_TIMEOUTS: ClassVar[dict[str, int]] = {
        **RegistryRequestRouter.OPERATION_TIMEOUTS,
        "capture_scope": 300,
    }
    ALLOWED_PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        **RegistryRequestRouter.ALLOWED_PARAMETER_KEYS,
        "capture_scope": frozenset({"hive", "path", "view", "max_entries"}),
    }
    REQUIRED_PARAMETER_KEYS: ClassVar[dict[str, frozenset[str]]] = {
        **RegistryRequestRouter.REQUIRED_PARAMETER_KEYS,
        "capture_scope": frozenset({"hive"}),
    }

    @staticmethod
    def _validate_parameters(operation: str, parameters: dict[str, Any]) -> None:
        RegistryRequestRouter._validate_parameters(operation, parameters)
        if operation == "capture_scope":
            value = parameters.get("max_entries")
            if value is not None and (
                type(value) is not int or value < 1 or value > 20_000
            ):
                raise ValueError
