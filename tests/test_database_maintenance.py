"""Στοχευμένες δοκιμές του Database tab χωρίς πραγματική SQL Server σύνδεση."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    """Φορτώνει ένα module από συγκεκριμένο τμήμα του repository."""

    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


odbc = types.ModuleType("pyodbc")
odbc.connect = Mock()
odbc.drivers = Mock(return_value=["ODBC Driver 17 for SQL Server"])
sys.modules["pyodbc"] = odbc

service_module = load_module(
    "database_maintenance_service_test",
    "client/app/database_maintenance_service.py",
)
router_module = load_module(
    "database_requests_test",
    "server/app/websocket/database_requests.py",
)
Service = service_module.DatabaseMaintenanceService
Router = router_module.DatabaseRequestRouter


class DatabaseServiceTests(unittest.TestCase):
    """Ελέγχει validation, ασφαλή SQL parameters και αποτελέσματα υπηρεσίας."""

    def setUp(self):
        odbc.connect.reset_mock()
        odbc.connect.side_effect = None
        odbc.drivers.reset_mock(return_value=True)
        odbc.drivers.return_value = ["ODBC Driver 17 for SQL Server"]
        self.connection = Mock()
        self.cursor = Mock()
        self.connection.cursor.return_value = self.cursor
        odbc.connect.return_value.__enter__ = Mock(return_value=self.connection)
        odbc.connect.return_value.__exit__ = Mock(return_value=False)
        self.service = Service()
        self.connection_string = (
            "Data Source=SQL01;Initial Catalog=InitialTest;"
            "User ID=sa;Password=top-secret;"
        )

    def test_invalid_date_is_rejected_before_connect(self):
        result = self.service.execute(
            "clean_mydata",
            self.connection_string,
            {"start_date": "20260230", "end_date": "20260301"},
        )
        self.assertFalse(result["success"])
        odbc.connect.assert_not_called()

    def test_unknown_and_sql_script_actions_are_rejected(self):
        for action in ("unknown", "execute_sql", "execute_script"):
            with self.subTest(action=action):
                result = self.service.execute(action, self.connection_string)
                self.assertFalse(result["success"])
        odbc.connect.assert_not_called()

    def test_mydata_cleanup_uses_parameters(self):
        self.cursor.fetchone.return_value = ("InitialTest",)
        self.cursor.rowcount = 7
        result = self.service.execute(
            "clean_mydata",
            self.connection_string,
            {"start_date": "20260901", "end_date": "20260910"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_rows"], 7)
        delete_call = next(
            call
            for call in self.cursor.execute.call_args_list
            if "DELETE FROM" in call.args[0]
        )
        self.assertNotIn("20260901", delete_call.args[0])
        self.assertEqual(delete_call.args[1:], ("20260901", "20260910"))

    def test_sales_info_returns_serializable_values(self):
        self.cursor.fetchone.side_effect = [
            ("InitialTest",),
            (125, service_module.datetime(2026, 1, 2, 12, 30)),
        ]
        result = self.service.execute("sales_trans_info", self.connection_string)
        self.assertTrue(result["success"])
        self.assertEqual(result["total_rows"], 125)
        self.assertEqual(result["first_date"], "2026-01-02 12:30:00")

    def test_query_timeout_is_set_on_connection_not_cursor(self):
        strict_connection = Mock(spec_set=["cursor", "timeout"])
        strict_cursor = Mock(spec_set=["execute", "fetchone"])
        strict_cursor.fetchone.side_effect = [("InitialTest",), (0, None)]
        strict_connection.cursor.return_value = strict_cursor
        odbc.connect.return_value.__enter__.return_value = strict_connection

        result = self.service.execute(
            "sales_trans_info",
            self.connection_string,
            timeout=321,
        )

        self.assertTrue(result["success"])
        self.assertEqual(strict_connection.timeout, 321)

    def test_connection_secret_is_redacted_from_errors(self):
        odbc.connect.side_effect = RuntimeError(
            f"Failed for {self.connection_string} user sa password top-secret"
        )
        result = self.service.execute("mydata_info", self.connection_string)
        self.assertFalse(result["success"])
        self.assertNotIn("top-secret", str(result))
        self.assertNotIn("User ID=sa", str(result))

    def test_database_names_are_quoted(self):
        self.assertEqual(self.service._quote_identifier("Db]Name"), "[Db]]Name]")
        self.assertEqual(self.service._quote_literal("Data'File"), "N'Data''File'")


class DatabaseRouterTests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει allowlist, ιδιωτική δρομολόγηση και timeout cleanup."""

    async def asyncSetUp(self):
        self.manager = types.SimpleNamespace(
            send_to_dashboard=AsyncMock(),
            send_to_client=AsyncMock(return_value=True),
        )
        self.router = Router(self.manager)
        self.dashboard = object()
        self.payload = {
            "type": "database_action",
            "request_id": str(uuid4()),
            "client_code": "CLIENT-1",
            "bo_connection_id": 2,
            "action": "clean_mydata",
            "parameters": {"start_date": "20260901", "end_date": "20260910"},
        }

    async def asyncTearDown(self):
        self.router.discard_dashboard(self.dashboard)

    async def test_request_forwards_only_allowed_fields(self):
        await self.router.request(
            self.dashboard,
            {**self.payload, "sql_text": "DROP TABLE x", "password": "secret"},
        )
        forwarded = self.manager.send_to_client.call_args.args[1]
        self.assertNotIn("sql_text", forwarded)
        self.assertNotIn("password", forwarded)
        self.assertEqual(forwarded["timeout"], 600)

    async def test_result_only_returns_to_requesting_dashboard(self):
        await self.router.request(self.dashboard, self.payload)
        result = {
            **self.payload,
            "type": "database_action_result",
            "success": True,
        }
        await self.router.result("CLIENT-1", result)
        self.manager.send_to_dashboard.assert_awaited_once_with(self.dashboard, result)
        self.assertFalse(self.router.pending)

    async def test_wrong_client_action_or_database_cannot_consume_request(self):
        await self.router.request(self.dashboard, self.payload)
        result = {**self.payload, "type": "database_action_result", "success": True}
        await self.router.result("OTHER", result)
        await self.router.result("CLIENT-1", {**result, "action": "shrink"})
        await self.router.result("CLIENT-1", {**result, "bo_connection_id": 3})
        self.manager.send_to_dashboard.assert_not_awaited()
        self.assertIn(self.payload["request_id"], self.router.pending)

    async def test_unexpected_parameters_are_rejected(self):
        await self.router.request(
            self.dashboard,
            {
                **self.payload,
                "parameters": {
                    "start_date": "20260901",
                    "end_date": "20260910",
                    "sql": "x",
                },
            },
        )
        self.manager.send_to_client.assert_not_awaited()
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]["success"])

    async def test_offline_client_cleans_pending(self):
        self.manager.send_to_client.return_value = False
        await self.router.request(self.dashboard, self.payload)
        self.assertFalse(self.router.pending)
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]["success"])


class DatabaseIntegrationSourceTests(unittest.TestCase):
    """Επιβεβαιώνει τις βασικές συνδέσεις UI και την απουσία SQL script action."""

    def test_tabs_are_named_ssms_and_database(self):
        source = (ROOT / "dashboard/app/views/client_manage_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('self.tabs.add("SSMS")', source)
        self.assertIn('self.tabs.add("Database")', source)

    def test_database_ui_does_not_offer_sql_script_execution(self):
        source = (ROOT / "dashboard/app/views/manage/database_tab.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("execute_sql", source)
        self.assertNotIn("execute_script", source)
        self.assertNotIn("Load .sql", source)

    def test_cli_does_not_offer_sql_script_execution(self):
        source = (ROOT / "dashboard/app/database_cli.py").read_text(encoding="utf-8")
        self.assertNotIn('"execute-sql"', source)
        self.assertNotIn('"execute-script"', source)


if __name__ == "__main__":
    unittest.main()
