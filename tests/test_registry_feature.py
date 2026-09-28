"""Windows Registry feature tests: service safety, profiles and server routing."""

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
    """Φορτώνει module απευθείας ώστε client/server `app` packages να μη συγκρούονται."""

    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Το SafeRegistryService κάνει absolute import app.registry_service στην κανονική εφαρμογή.
# Στα tests δημιουργούμε μόνο το ελάχιστο package namespace που χρειάζεται.
client_app = types.ModuleType("app")
client_app.__path__ = []
sys.modules["app"] = client_app
base_registry_module = load_module("app.registry_service", "client/app/registry_service.py")
safe_registry_module = load_module("app.registry_service_safe", "client/app/registry_service_safe.py")
SafeRegistryService = safe_registry_module.SafeRegistryService

# Ο server router δεν εξαρτάται από το server `app` package, άρα φορτώνεται με unique name.
router_module = load_module("registry_requests_test", "server/app/websocket/registry_requests.py")
RegistryRequestRouter = router_module.RegistryRequestRouter

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


@unittest.skipUnless(sys.platform == "win32", "Registry integration tests require Windows")
class RegistryServiceWindowsTests(unittest.TestCase):
    """Runs only against an isolated HKCU test key."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = SafeRegistryService(self.temp_dir.name)
        self.test_root = rf"Software\MoonHardRemoteV2\Tests\{uuid.uuid4()}"

    def tearDown(self) -> None:
        try:
            self.service.delete_key("HKCU", self.test_root, recursive=True)
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_create_key_backup_can_remove_new_key_on_restore(self) -> None:
        result = self.service.create_key("HKCU", self.test_root)
        self.assertTrue(result["backup_id"])
        listing = self.service.list_key("HKCU", self.test_root)
        self.assertEqual(listing["path"], self.test_root)

        restored = self.service.restore_backup(result["backup_id"])
        self.assertFalse(restored["target_existed_before_original_change"])
        with self.assertRaises(FileNotFoundError):
            self.service.list_key("HKCU", self.test_root)

    def test_round_trip_supported_value_types(self) -> None:
        self.service.create_key("HKCU", self.test_root)
        values = [
            ("Text", "REG_SZ", "MoonHard"),
            ("Expand", "REG_EXPAND_SZ", r"%TEMP%\MoonHard"),
            ("Dword", "REG_DWORD", "0x2A"),
            ("Qword", "REG_QWORD", "4294967297"),
            ("Multi", "REG_MULTI_SZ", "one\ntwo\nthree"),
            ("Binary", "REG_BINARY", "DE AD BE EF"),
        ]
        for name, value_type, value in values:
            result = self.service.set_value("HKCU", self.test_root, name, value_type, value)
            self.assertTrue(result["backup_id"])
            current = self.service.get_value("HKCU", self.test_root, name)["value"]
            self.assertEqual(current["type"], value_type)

        self.assertEqual(self.service.get_value("HKCU", self.test_root, "Dword")["value"]["data"], 42)
        self.assertEqual(self.service.get_value("HKCU", self.test_root, "Multi")["value"]["data"], ["one", "two", "three"])

    def test_snapshot_compare_and_restore(self) -> None:
        self.service.set_value("HKCU", self.test_root, "Mode", "REG_SZ", "before")
        snapshot = self.service.snapshot("HKCU", self.test_root)
        self.service.set_value("HKCU", self.test_root, "Mode", "REG_SZ", "after")
        self.service.set_value("HKCU", self.test_root, "Added", "REG_DWORD", 1)

        diff = self.service.compare_snapshot(snapshot["backup_id"])
        self.assertGreaterEqual(diff["different_count"], 2)
        self.assertTrue(diff["changed"])
        self.assertTrue(diff["added"])

        self.service.restore_backup(snapshot["backup_id"])
        restored = self.service.get_value("HKCU", self.test_root, "Mode")["value"]
        self.assertEqual(restored["data"], "before")
        with self.assertRaises(FileNotFoundError):
            self.service.get_value("HKCU", self.test_root, "Added")

    def test_export_import_preview_supports_all_ui_types(self) -> None:
        self.service.set_value("HKCU", self.test_root, "Text", "REG_SZ", "abc")
        self.service.set_value("HKCU", self.test_root, "Expand", "REG_EXPAND_SZ", r"%TEMP%\abc")
        self.service.set_value("HKCU", self.test_root, "Dword", "REG_DWORD", 10)
        self.service.set_value("HKCU", self.test_root, "Qword", "REG_QWORD", 9999999999)
        self.service.set_value("HKCU", self.test_root, "Multi", "REG_MULTI_SZ", ["a", "b"])
        self.service.set_value("HKCU", self.test_root, "Binary", "REG_BINARY", "01 02 FF")

        exported = self.service.export_reg("HKCU", self.test_root)
        preview = self.service.import_reg_preview(exported["reg_text"])
        by_type = {item["value_type"] for item in preview["operations"]}
        self.assertTrue({"REG_SZ", "REG_EXPAND_SZ", "REG_DWORD", "REG_QWORD", "REG_MULTI_SZ", "REG_BINARY"}.issubset(by_type))

    def test_profile_check_dry_run_and_apply(self) -> None:
        self.service.set_value("HKCU", self.test_root, "Mode", "REG_SZ", "expected")
        current = self.service.get_value("HKCU", self.test_root, "Mode")["value"]
        profile = self.service.profile_save(
            "Test Profile",
            [{
                "hive": "HKCU",
                "path": self.test_root,
                "view": "default",
                "value_name": "Mode",
                "value_type": current["type"],
                "value": current["data"],
            }],
        )

        self.assertEqual(self.service.profile_check(profile["profile_id"])["problem_count"], 0)
        self.service.set_value("HKCU", self.test_root, "Mode", "REG_SZ", "wrong")
        self.assertEqual(self.service.profile_check(profile["profile_id"])["problem_count"], 1)

        dry_run = self.service.profile_apply(profile["profile_id"], mode="all", dry_run=True)
        self.assertEqual(dry_run["planned_count"], 1)
        self.assertEqual(dry_run["applied_count"], 0)

        applied = self.service.profile_apply(profile["profile_id"], mode="all", dry_run=False)
        self.assertEqual(applied["applied_count"], 1)
        self.assertEqual(self.service.get_value("HKCU", self.test_root, "Mode")["value"]["data"], "expected")

    def test_search_is_bounded_and_returns_value_matches(self) -> None:
        self.service.set_value("HKCU", self.test_root, "NeedleName", "REG_SZ", "NeedleData")
        result = self.service.search(
            "needle",
            hive="HKCU",
            path=self.test_root,
            max_results=20,
            max_depth=3,
        )
        self.assertGreaterEqual(result["count"], 1)
        self.assertTrue(any(item.get("kind") == "value" for item in result["results"]))


class _FakeManager:
    def __init__(self, supports: bool = True) -> None:
        self.supports = supports
        self.to_dashboard: list[tuple[object, dict]] = []
        self.to_client: list[tuple[str, dict]] = []

    def client_supports(self, client_code: str, capability: str) -> bool:
        return self.supports and capability == "registry_v1"

    async def send_to_dashboard(self, dashboard, message: dict) -> None:
        self.to_dashboard.append((dashboard, message))

    async def send_to_client(self, client_code: str, message: dict) -> bool:
        self.to_client.append((client_code, message))
        return True


class RegistryRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_client_without_registry_capability(self) -> None:
        manager = _FakeManager(supports=False)
        router = RegistryRequestRouter(manager)
        dashboard = object()
        await router.request(
            dashboard,
            {
                "type": "registry_request",
                "request_id": str(uuid.uuid4()),
                "client_code": "client-1",
                "operation": "context",
                "parameters": {},
            },
        )
        self.assertFalse(manager.to_client)
        self.assertEqual(manager.to_dashboard[-1][1]["success"], False)
        self.assertIn("does not support Registry Center", manager.to_dashboard[-1][1]["error"])

    async def test_routes_valid_result_only_to_origin_dashboard(self) -> None:
        manager = _FakeManager(supports=True)
        router = RegistryRequestRouter(manager)
        dashboard = object()
        request_id = str(uuid.uuid4())
        await router.request(
            dashboard,
            {
                "type": "registry_request",
                "request_id": request_id,
                "client_code": "client-1",
                "operation": "list_key",
                "parameters": {"hive": "HKCU", "path": "Software", "view": "default"},
            },
        )
        self.assertEqual(manager.to_client[-1][0], "client-1")
        self.assertEqual(manager.to_client[-1][1]["type"], "registry_request")

        await router.result(
            "client-1",
            {
                "type": "registry_result",
                "request_id": request_id,
                "operation": "list_key",
                "success": True,
                "subkeys": [],
                "values": [],
            },
        )
        self.assertIs(manager.to_dashboard[-1][0], dashboard)
        self.assertEqual(manager.to_dashboard[-1][1]["client_code"], "client-1")
        self.assertNotIn(request_id, router.pending)

    async def test_rejects_unexpected_parameters(self) -> None:
        manager = _FakeManager(supports=True)
        router = RegistryRequestRouter(manager)
        await router.request(
            object(),
            {
                "type": "registry_request",
                "request_id": str(uuid.uuid4()),
                "client_code": "client-1",
                "operation": "list_key",
                "parameters": {"hive": "HKCU", "evil": "data"},
            },
        )
        self.assertFalse(manager.to_client)
        self.assertEqual(manager.to_dashboard[-1][1]["error"], "Invalid registry request.")


if __name__ == "__main__":
    unittest.main()
