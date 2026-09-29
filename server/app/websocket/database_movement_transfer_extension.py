"""Server-side allowlist/progress extension for movement transfer actions."""

from __future__ import annotations

from app.websocket.database_requests import DatabaseRequestRouter


CAPABILITY = "database_movement_transfer_v1"
STATIONS_ACTION = "movement_stations"
RECEIPT_SEARCH_ACTION = "movement_receipt_search"
DATE_TRANSFER_ACTION = "movement_transfer_date"
RECEIPT_TRANSFER_ACTION = "movement_transfer_receipt"
ACTIONS = {
    STATIONS_ACTION,
    RECEIPT_SEARCH_ACTION,
    DATE_TRANSFER_ACTION,
    RECEIPT_TRANSFER_ACTION,
}
PROGRESS_ACTIONS = {DATE_TRANSFER_ACTION, RECEIPT_TRANSFER_ACTION}


def install_database_movement_transfer_extension(websocket_routes) -> None:
    """Extends the existing DatabaseRequestRouter with controlled movement transfer actions."""

    router = websocket_routes.database_requests
    if getattr(router, "_movement_transfer_extension_installed", False):
        return

    router.ACTION_TIMEOUTS[STATIONS_ACTION] = 60
    router.PARAMETER_KEYS[STATIONS_ACTION] = frozenset()

    router.ACTION_TIMEOUTS[RECEIPT_SEARCH_ACTION] = 120
    router.PARAMETER_KEYS[RECEIPT_SEARCH_ACTION] = frozenset(
        {"note_no", "search_date", "station_oid"}
    )

    router.ACTION_TIMEOUTS[DATE_TRANSFER_ACTION] = 600
    router.PARAMETER_KEYS[DATE_TRANSFER_ACTION] = frozenset(
        {"mode", "old_date", "real_date", "new_date", "station_oid"}
    )

    router.ACTION_TIMEOUTS[RECEIPT_TRANSFER_ACTION] = 600
    router.PARAMETER_KEYS[RECEIPT_TRANSFER_ACTION] = frozenset(
        {
            "source",
            "pos_hdr",
            "note_no",
            "note_code",
            "old_date",
            "new_date",
            "station_oid",
        }
    )

    original_request = router.request
    original_progress = router.progress

    async def extended_request(dashboard, data: dict) -> None:
        client_code = data.get("client_code")
        if (
            data.get("action") in ACTIONS
            and isinstance(client_code, str)
            and client_code
            and not router.manager.client_supports(client_code, CAPABILITY)
        ):
            action = str(data.get("action") or "")
            await router.manager.send_to_dashboard(
                dashboard,
                router.error_payload(
                    str(data.get("request_id") or ""),
                    client_code,
                    data.get("bo_connection_id")
                    if type(data.get("bo_connection_id")) is int
                    else 1,
                    action,
                    "Client update required for Movement Transfer.",
                ),
            )
            return

        await original_request(dashboard, data)

    async def extended_progress(client_code: str, data: dict) -> None:
        action = data.get("action")
        if action not in PROGRESS_ACTIONS:
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
        if pending.action != action:
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
                "action": action,
                "stage": stage,
                "percent": percent,
                "message": message,
            },
        )

    router.request = extended_request
    router.progress = extended_progress
    router._movement_transfer_extension_installed = True
