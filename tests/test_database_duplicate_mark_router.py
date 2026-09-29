from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_APP = ROOT / "server" / "app"
SERVER_WS = SERVER_APP / "websocket"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


app_package = types.ModuleType("app")
app_package.__path__ = [str(SERVER_APP)]
sys.modules["app"] = app_package
websocket_package = types.ModuleType("app.websocket")
websocket_package.__path__ = [str(SERVER_WS)]
sys.modules["app.websocket"] = websocket_package

router_module = _load_module(
    "app.websocket.database_requests",
    SERVER_WS / "database_requests.py",
)
extension_module = _load_module(
    "app.websocket.database_duplicate_mark_extension",
    SERVER_WS / "database_duplicate_mark_extension.py",
)


class FakeManager:
    def __init__(self, capabilities: set[str] | None = None):
        self.sent: list[tuple[object, dict]] = []
        self.capabilities = capabilities or set()

    async def send_to_dashboard(self, dashboard, payload):
        self.sent.append((dashboard, payload))

    async def send_to_client(self, _client_code, _payload):
        return True

    def client_supports(self, _client_code: str, capability: str) -> bool:
        return capability in self.capabilities


class FakeRoutes:
    def __init__(self, database_requests):
        self.database_requests = database_requests


class DuplicateMarkRouterTests(unittest.TestCase):
    def test_install_adds_allowlisted_action(self):
        manager = FakeManager()
        router = router_module.DatabaseRequestRouter(manager)
        extension_module.install_database_duplicate_mark_extension(FakeRoutes(router))

        self.assertEqual(router.ACTION_TIMEOUTS["delete_duplicate_mark"], 600)
        self.assertEqual(
            router.PARAMETER_KEYS["delete_duplicate_mark"],
            frozenset(),
        )

    def test_old_client_is_rejected_with_clear_update_error(self):
        manager = FakeManager()
        router = router_module.DatabaseRequestRouter(manager)
        extension_module.install_database_duplicate_mark_extension(FakeRoutes(router))
        dashboard = object()

        asyncio.run(
            router.request(
                dashboard,
                {
                    "type": "database_action",
                    "request_id": "00000000-0000-0000-0000-000000000002",
                    "client_code": "PC-OLD",
                    "bo_connection_id": 1,
                    "action": "delete_duplicate_mark",
                    "parameters": {},
                },
            )
        )

        self.assertEqual(len(manager.sent), 1)
        _, payload = manager.sent[0]
        self.assertFalse(payload["success"])
        self.assertIn("Client update required", payload["error"])

    def test_step_progress_is_forwarded(self):
        manager = FakeManager({"database_duplicate_mark_v1"})
        router = router_module.DatabaseRequestRouter(manager)
        extension_module.install_database_duplicate_mark_extension(FakeRoutes(router))
        dashboard = object()
        request_id = "00000000-0000-0000-0000-000000000001"
        router.pending[request_id] = router_module.PendingDatabaseRequest(
            dashboard=dashboard,
            client_code="PC-1",
            bo_connection_id=1,
            action="delete_duplicate_mark",
        )

        asyncio.run(
            router.progress(
                "PC-1",
                {
                    "type": router.PROGRESS_TYPE,
                    "request_id": request_id,
                    "client_code": "PC-1",
                    "bo_connection_id": 1,
                    "action": "delete_duplicate_mark",
                    "stage": "success_warning",
                    "percent": 45,
                    "message": "Step 1 warning. Continuing...",
                },
            )
        )

        self.assertEqual(len(manager.sent), 1)
        _, payload = manager.sent[0]
        self.assertEqual(payload["action"], "delete_duplicate_mark")
        self.assertEqual(payload["percent"], 45)
        self.assertEqual(payload["stage"], "success_warning")


if __name__ == "__main__":
    unittest.main()
