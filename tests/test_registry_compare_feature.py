"""Registry Compare service/router tests."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Client service namespace.
client_app = types.ModuleType("app")
client_app.__path__ = []
sys.modules["app"] = client_app
load_module("app.registry_service", "client/app/registry_service.py")
load_module("app.registry_service_safe", "client/app/registry_service_safe.py")
compare_service_module = load_module(
    "app.registry_compare_service",
    "client/app/registry_compare_service.py",
)
RegistryCompareService = compare_service_module.RegistryCompareService

try:
    import winreg  # noqa: F401
except ImportError:  # pragma: no cover
    winreg = None


@unittest.skipUnless(sys.platform == "win32", "Registry integration tests require Windows")
class RegistryCompareServiceWindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = RegistryCompareService(self.temp_dir.name)
        self.test_root = rf"Software\MoonHardRemoteV2\CompareTests\{uuid.uuid4()}"

    def tearDown(self) -> None:
        try:
            self.service.delete_key("HKCU", self.test_root, recursive=True)
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_capture_scope_is_read_only_and_returns_tree(self) -> None:
        self.service.set_value("HKCU", self.test_root, "Mode", "REG_SZ", "A")
        before = sorted(self.service.backup_root.glob("*.json"))
        captured = self.service.capture_scope("HKCU", self.test_root, max_entries=100)
        after = sorted(self.service.backup_root.glob("*.json"))

        self.assertTrue(captured["exists"])
        self.assertEqual(captured["path"], self.test_root)
        self.assertEqual(captured["tree"]["values"][0]["name"], "Mode")
        self.assertEqual(before, after)

    def test_capture_missing_scope_returns_empty_not_error(self) -> None:
        captured = self.service.capture_scope(
            "HKCU",
            self.test_root + r"\DoesNotExist",
            max_entries=100,
        )
        self.assertFalse(captured["exists"])
        self.assertEqual(captured["entry_count"], 0)
        self.assertEqual(captured["tree"], {"values": [], "subkeys": {}})


# Replace the temporary client app namespace with the server namespace.
for name in list(sys.modules):
    if name == "app" or name.startswith("app."):
        sys.modules.pop(name, None)
server_app = types.ModuleType("app")
server_app.__path__ = []
server_websocket = types.ModuleType("app.websocket")
server_websocket.__path__ = []
sys.modules["app"] = server_app
sys.modules["app.websocket"] = server_websocket
load_module("app.websocket.registry_requests", "server/app/websocket/registry_requests.py")
compare_router_module = load_module(
    "app.websocket.registry_compare_requests",
    "server/app/websocket/registry_compare_requests.py",
)
RegistryCompareRequestRouter = compare_router_module.RegistryCompareRequestRouter


class _FakeManager:
    def __init__(self) -> None:
        self.to_dashboard: list[tuple[object, dict]] = []
        self.to_client: list[tuple[str, dict]] = []

    def client_supports(self, _client_code: str, capability: str) -> bool:
        return capability == "registry_v1"

    async def send_to_dashboard(self, dashboard, message: dict) -> None:
        self.to_dashboard.append((dashboard, message))

    async def send_to_client(self, client_code: str, message: dict) -> bool:
        self.to_client.append((client_code, message))
        return True


class RegistryCompareRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_scope_is_allowlisted_and_forwarded(self) -> None:
        manager = _FakeManager()
        router = RegistryCompareRequestRouter(manager)
        request_id = str(uuid.uuid4())
        await router.request(
            object(),
            {
                "type": "registry_request",
                "request_id": request_id,
                "client_code": "client-b",
                "operation": "capture_scope",
                "parameters": {
                    "hive": "HKLM",
                    "path": r"SOFTWARE\MoonHard",
                    "view": "64",
                    "max_entries": 10000,
                },
            },
        )
        self.assertEqual(manager.to_client[-1][0], "client-b")
        self.assertEqual(manager.to_client[-1][1]["operation"], "capture_scope")
        self.assertIn(request_id, router.pending)

    async def test_capture_scope_rejects_oversized_limit(self) -> None:
        manager = _FakeManager()
        router = RegistryCompareRequestRouter(manager)
        await router.request(
            object(),
            {
                "type": "registry_request",
                "request_id": str(uuid.uuid4()),
                "client_code": "client-b",
                "operation": "capture_scope",
                "parameters": {"hive": "HKLM", "max_entries": 20001},
            },
        )
        self.assertFalse(manager.to_client)
        self.assertEqual(manager.to_dashboard[-1][1]["success"], False)


if __name__ == "__main__":
    unittest.main()
