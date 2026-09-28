"""Registry WebSocket extension για το υπάρχον WebSocketRoutes instance."""

from __future__ import annotations

from typing import Any

from app.websocket.connection_manager import connection_manager
from app.websocket.registry_requests import RegistryRequestRouter
from app.websocket.registry_compare_requests import RegistryCompareRequestRouter


class _RegistryAwareServerWebSocket:
    """WebSocket proxy που καταναλώνει Registry protocol messages."""

    def __init__(self, raw_websocket, router: RegistryRequestRouter, role: str) -> None:
        self._raw = raw_websocket
        self._router = router
        self._role = role
        self._client_code = ""

    async def receive_json(self, *args, **kwargs):
        while True:
            data = await self._raw.receive_json(*args, **kwargs)
            message_type = str(data.get("type") or "") if isinstance(data, dict) else ""

            if self._role == "client":
                if message_type == "register":
                    self._client_code = str(data.get("client_code") or "")
                    return data
                if message_type == RegistryRequestRouter.RESULT_TYPE:
                    await self._router.result(self._client_code, data)
                    continue
                if message_type == RegistryRequestRouter.PROGRESS_TYPE:
                    await self._router.progress(self._client_code, data)
                    continue
                return data

            if self._role == "dashboard":
                if message_type == RegistryRequestRouter.REQUEST_TYPE:
                    await self._router.request(self, data)
                    continue
                return data

            return data

    async def send_json(self, *args, **kwargs):
        return await self._raw.send_json(*args, **kwargs)

    async def send_text(self, *args, **kwargs):
        return await self._raw.send_text(*args, **kwargs)

    async def send_bytes(self, *args, **kwargs):
        return await self._raw.send_bytes(*args, **kwargs)

    async def close(self, *args, **kwargs):
        return await self._raw.close(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def install_registry_extension(websocket_routes_instance) -> RegistryRequestRouter:
    """Τυλίγει τα δύο websocket loops και επιστρέφει τον Registry router."""

    existing = getattr(websocket_routes_instance, "registry_requests", None)
    if isinstance(existing, RegistryRequestRouter):
        return existing

    registry_requests = RegistryCompareRequestRouter(connection_manager)
    websocket_routes_instance.registry_requests = registry_requests

    original_client_socket = websocket_routes_instance.client_socket
    original_dashboard_socket = websocket_routes_instance.dashboard_socket

    async def client_socket(raw_websocket) -> None:
        proxy = _RegistryAwareServerWebSocket(raw_websocket, registry_requests, "client")
        await original_client_socket(proxy)

    async def dashboard_socket(raw_websocket) -> None:
        proxy = _RegistryAwareServerWebSocket(raw_websocket, registry_requests, "dashboard")
        try:
            await original_dashboard_socket(proxy)
        finally:
            registry_requests.discard_dashboard(proxy)

    websocket_routes_instance.client_socket = client_socket
    websocket_routes_instance.dashboard_socket = dashboard_socket
    return registry_requests