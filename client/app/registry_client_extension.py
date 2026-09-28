"""Registry protocol extension χωρίς αλλαγές στον μεγάλο client_agent.py."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.client_agent import MoonHardClientAgent
from app.registry_service_safe import SafeRegistryService


logger = logging.getLogger(__name__)


class _RegistryAwareWebSocket:
    """Proxy που καταναλώνει Registry requests πριν τα δει ο legacy listener."""

    def __init__(self, raw_websocket, agent: "RegistryEnabledClientAgent") -> None:
        self._raw = raw_websocket
        self._agent = agent

    async def recv(self):
        while True:
            message = await self._raw.recv()
            try:
                payload = json.loads(message)
            except (TypeError, ValueError):
                return message

            if payload.get("type") != "registry_request":
                return message

            await self._agent._handle_registry_request(self, payload)

    async def send(self, data):
        return await self._raw.send(data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


class RegistryEnabledClientAgent(MoonHardClientAgent):
    """Προσθέτει registry_v1 capability και Registry request handling."""

    def __init__(self) -> None:
        super().__init__()
        self.registry_service = SafeRegistryService()

    def _create_register_message(self) -> dict:
        message = super()._create_register_message()
        capabilities = list(message.get("capabilities") or [])
        if "registry_v1" not in capabilities:
            capabilities.append("registry_v1")
        message["capabilities"] = capabilities
        return message

    async def _listen_forever(self, websocket) -> None:
        """Τυλίγει το socket, κρατώντας ανέπαφο το υπάρχον dispatch του agent."""

        await super()._listen_forever(_RegistryAwareWebSocket(websocket, self))

    async def _handle_registry_request(self, websocket, payload: dict[str, Any]) -> None:
        """Εκτελεί Registry operation σε worker thread και streamάρει bounded progress."""

        request_id = str(payload.get("request_id") or "")
        operation = str(payload.get("operation") or "")
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}

        progress_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        event_loop = asyncio.get_running_loop()

        def report_progress(progress: dict[str, Any]) -> None:
            event_loop.call_soon_threadsafe(progress_queue.put_nowait, dict(progress))

        def run_operation() -> dict[str, Any]:
            try:
                return self.registry_service.execute(
                    operation,
                    parameters,
                    progress_callback=report_progress,
                )
            finally:
                event_loop.call_soon_threadsafe(progress_queue.put_nowait, None)

        try:
            logger.info(
                "Registry request received. request_id=%s operation=%s",
                request_id,
                operation,
            )
            operation_task = asyncio.create_task(asyncio.to_thread(run_operation))

            while True:
                progress = await progress_queue.get()
                if progress is None:
                    break
                await websocket.send(
                    json.dumps(
                        {
                            "type": "registry_progress",
                            "request_id": request_id,
                            "client_code": self.identity["client_code"],
                            "operation": operation,
                            **progress,
                        },
                        ensure_ascii=False,
                    )
                )

            result = await operation_task
        except Exception as exc:
            logger.exception("Registry request failed. operation=%s", operation)
            result = {
                "operation": operation,
                "success": False,
                "error": str(exc)[:2000],
            }

        await websocket.send(
            json.dumps(
                {
                    "type": "registry_result",
                    "request_id": request_id,
                    "client_code": self.identity["client_code"],
                    "operation": operation,
                    **result,
                },
                ensure_ascii=False,
            )
        )
