"""Server-side allowlist/progress extension για τη Διαγραφή διπλών ΜΑΡΚ."""

from __future__ import annotations

from app.websocket.database_requests import DatabaseRequestRouter


ACTION = "delete_duplicate_mark"
CAPABILITY = "database_duplicate_mark_v1"


def install_database_duplicate_mark_extension(websocket_routes) -> None:
    """Επεκτείνει μόνο το υπάρχον DatabaseRequestRouter instance."""

    router = websocket_routes.database_requests
    if getattr(router, "_duplicate_mark_extension_installed", False):
        return

    router.ACTION_TIMEOUTS[ACTION] = 600
    router.PARAMETER_KEYS[ACTION] = frozenset()

    original_request = router.request
    original_progress = router.progress

    async def extended_request(dashboard, data: dict) -> None:
        client_code = data.get("client_code")
        if (
            data.get("action") == ACTION
            and isinstance(client_code, str)
            and client_code
            and not router.manager.client_supports(client_code, CAPABILITY)
        ):
            await router.manager.send_to_dashboard(
                dashboard,
                router.error_payload(
                    str(data.get("request_id") or ""),
                    client_code,
                    data.get("bo_connection_id")
                    if type(data.get("bo_connection_id")) is int
                    else 1,
                    ACTION,
                    "Client update required for Duplicate MARK cleanup.",
                ),
            )
            return

        await original_request(dashboard, data)

    async def extended_progress(client_code: str, data: dict) -> None:
        if data.get("action") != ACTION:
            await original_progress(client_code, data)
            return

        request_id = data.get("request_id")
        if not isinstance(request_id, str):
            return

        pending = router.pending.get(request_id)
        if not pending or pending.client_code != client_code:
            return
        if data.get("type") != DatabaseRequestRouter.PROGRESS_TYPE:
            return
        if data.get("bo_connection_id") != pending.bo_connection_id:
            return
        if pending.action != ACTION:
            return

        message = data.get("message")
        stage = data.get("stage")
        percent = data.get("percent")
        if not isinstance(message, str) or not message or len(message) > 2000:
            return
        if not isinstance(stage, str) or not stage or len(stage) > 64:
            return
        if type(percent) is not int or not 0 <= percent <= 100:
            return

        await router.manager.send_to_dashboard(
            pending.dashboard,
            {
                "type": DatabaseRequestRouter.PROGRESS_TYPE,
                "request_id": request_id,
                "client_code": client_code,
                "bo_connection_id": pending.bo_connection_id,
                "action": ACTION,
                "stage": stage,
                "percent": percent,
                "message": message,
            },
        )

    router.request = extended_request
    router.progress = extended_progress
    router._duplicate_mark_extension_installed = True
