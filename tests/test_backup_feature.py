"""Στοχευμένες δοκιμές backup engine, scheduler, routing, UI και CLI."""

import ast
import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    """Φορτώνει module απευθείας από το repository."""

    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if "pyodbc" not in sys.modules:
    odbc = types.ModuleType("pyodbc")
    odbc.connect = Mock()
    odbc.drivers = Mock(return_value=["ODBC Driver 17 for SQL Server"])
    sys.modules["pyodbc"] = odbc


backup_module = load_module("backup_service_test", "client/app/backup_service.py")
router_module = load_module(
    "backup_requests_test", "server/app/websocket/backup_requests.py"
)
Validator = backup_module.BackupSettingsValidator
Store = backup_module.BackupStateStore
Router = router_module.BackupRequestRouter


def settings(**changes):
    """Δημιουργεί πλήρες έγκυρο backup settings payload."""

    result = {
        "destination_type": "local",
        "destination_path": r"D:\SQLBackups",
        "staging_path": "",
        "cloud_remote": "",
        "retention_mode": "keep_last",
        "retention_count": 7,
        "compression": True,
        "copy_only": True,
    }
    result.update(changes)
    return result


def schedule(**changes):
    """Δημιουργεί πλήρες έγκυρο schedule payload."""

    result = {
        "schedule_id": "",
        "name": "Nightly InitialTest",
        "bo_connection_id": 1,
        "frequency": "daily",
        "time": "02:00",
        "weekday": 0,
        "day_of_month": 1,
        "enabled": True,
        "settings": settings(),
    }
    result.update(changes)
    return result


class BackupValidationTests(unittest.TestCase):
    """Ελέγχει paths, retention modes και schedule υπολογισμούς."""

    def test_all_requested_retention_modes_are_supported(self):
        for mode in ("replace", "keep_all", "keep_last"):
            with self.subTest(mode=mode):
                self.assertEqual(
                    Validator.backup_settings(settings(retention_mode=mode))[
                        "retention_mode"
                    ],
                    mode,
                )

    def test_local_unc_and_cloud_destinations_are_supported(self):
        local = Validator.backup_settings(settings())
        unc = Validator.backup_settings(
            settings(destination_type="unc", destination_path=r"\\NAS01\Backups")
        )
        cloud = Validator.backup_settings(
            settings(
                destination_type="cloud",
                destination_path="",
                staging_path=r"C:\BackupStage",
                cloud_remote="mega:MoonHard/SQL",
            )
        )
        self.assertEqual(local["destination_type"], "local")
        self.assertTrue(unc["destination_path"].startswith("\\\\"))
        self.assertEqual(cloud["cloud_remote"], "mega:MoonHard/SQL")

    def test_relative_paths_and_parent_cloud_segments_are_rejected(self):
        with self.assertRaises(ValueError):
            Validator.backup_settings(settings(destination_path="Backups"))
        with self.assertRaises(ValueError):
            Validator.backup_settings(
                settings(
                    destination_type="cloud",
                    destination_path="",
                    staging_path=r"C:\Stage",
                    cloud_remote="mega:../secret",
                )
            )

    def test_daily_next_run_uses_client_local_time(self):
        now = datetime(2026, 9, 11, 3, 0, tzinfo=timezone(timedelta(hours=3)))
        result = Validator.schedule(schedule(time="02:00"), now=now)
        self.assertEqual(result["next_run_at"], "2026-09-12T02:00:00+03:00")

    def test_weekly_and_monthly_next_run(self):
        now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
        weekly = Validator.schedule(
            schedule(frequency="weekly", weekday=0, time="01:30"), now=now
        )
        monthly = Validator.schedule(
            schedule(frequency="monthly", day_of_month=31, time="01:30"), now=now
        )
        self.assertEqual(weekly["next_run_at"], "2026-09-14T01:30:00+00:00")
        self.assertEqual(monthly["next_run_at"], "2026-09-30T01:30:00+00:00")


class BackupStateStoreTests(unittest.TestCase):
    """Ελέγχει persistence, due claiming και ασφαλή history updates."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "backup_state.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_schedule_round_trip_and_delete(self):
        saved = self.store.save_schedule(schedule())
        self.assertTrue((Path(self.temp.name) / "backup_state.json").is_file())
        loaded = self.store.get_schedule(saved["schedule_id"])
        self.assertEqual(loaded["name"], "Nightly InitialTest")
        self.assertTrue(self.store.delete_schedule(saved["schedule_id"]))
        self.assertIsNone(self.store.get_schedule(saved["schedule_id"]))

    def test_due_schedule_is_claimed_only_once(self):
        saved = self.store.save_schedule(schedule())
        state = self.store._load_unlocked()
        state["schedules"][0]["next_run_at"] = (
            datetime.now().astimezone() - timedelta(minutes=1)
        ).isoformat()
        self.store._write_unlocked(state)
        first = self.store.claim_due()
        second = self.store.claim_due()
        self.assertEqual(first[0]["schedule_id"], saved["schedule_id"])
        self.assertEqual(second, [])

    def test_history_tracks_retryable_cloud_upload(self):
        item = self.store.append_history(
            {
                "status": "upload_failed",
                "retry_count": 0,
                "next_retry_at": (
                    datetime.now().astimezone() - timedelta(minutes=1)
                ).isoformat(),
                "started_at": datetime.now().astimezone().isoformat(),
            }
        )
        retryable = self.store.retryable_uploads()
        self.assertEqual(retryable[0]["history_id"], item["history_id"])
        updated = self.store.update_history(item["history_id"], {"status": "completed"})
        self.assertEqual(updated["status"], "completed")

    def test_local_retention_deletes_only_moonhard_backup_pattern(self):
        folder = Path(self.temp.name)
        for name in (
            "InitialTest_20260909_020000_000.bak",
            "InitialTest_20260910_020000_000.bak",
            "InitialTest_20260911_020000_000.bak",
            "manual-important.bak",
        ):
            (folder / name).write_bytes(b"backup")
        deleted = backup_module.SqlServerBackupService._local_keep_last(
            str(folder), "InitialTest", 2
        )
        self.assertEqual(len(deleted), 1)
        self.assertTrue((folder / "manual-important.bak").exists())


class SqlBackupCommandTests(unittest.TestCase):
    """Ελέγχει ότι το SQL backup χρησιμοποιεί ασφαλές path parameter και verification."""

    def setUp(self):
        self.connection = Mock()
        self.cursor = Mock()
        self.cursor.fetchone.return_value = (77,)
        self.cursor.description = None
        self.cursor.nextset.return_value = False
        self.connection.cursor.return_value = self.cursor
        context = Mock()
        context.__enter__ = Mock(return_value=self.connection)
        context.__exit__ = Mock(return_value=False)
        backup_module.pyodbc.connect = Mock(return_value=context)
        backup_module.pyodbc.drivers = Mock(
            return_value=["ODBC Driver 17 for SQL Server"]
        )
        adapter = Mock()
        self.service = backup_module.SqlServerBackupService(adapter)
        self.connection_string = (
            "Data Source=SQL01;Initial Catalog=InitialTest;User ID=sa;Password=secret;"
        )

    def test_backup_uses_parameterized_path_and_safe_options(self):
        self.service._run_sql_backup(
            self.connection_string,
            "InitialTest",
            r"D:\SQLBackups\InitialTest_test.bak",
            settings(),
            progress_callback=None,
        )
        backup_call = next(
            call
            for call in self.cursor.execute.call_args_list
            if "BACKUP DATABASE" in call.args[0]
        )
        self.assertNotIn(r"D:\SQLBackups", backup_call.args[0])
        self.assertEqual(backup_call.args[1], r"D:\SQLBackups\InitialTest_test.bak")
        for option in ("CHECKSUM", "COPY_ONLY", "COMPRESSION", "STATS = 5"):
            self.assertIn(option, backup_call.args[0])

    def test_verifyonly_uses_parameterized_path_and_checksum(self):
        self.service._verify_backup(
            self.connection_string,
            r"D:\SQLBackups\InitialTest_test.bak",
        )
        verify_call = next(
            call
            for call in self.cursor.execute.call_args_list
            if "RESTORE VERIFYONLY" in call.args[0]
        )
        self.assertNotIn(r"D:\SQLBackups", verify_call.args[0])
        self.assertIn("WITH CHECKSUM", verify_call.args[0])
        self.assertEqual(verify_call.args[1], r"D:\SQLBackups\InitialTest_test.bak")


class BackupRouterTests(unittest.IsolatedAsyncioTestCase):
    """Ελέγχει strict allowlist και ιδιωτική συσχέτιση client/dashboard."""

    async def asyncSetUp(self):
        self.manager = types.SimpleNamespace(
            send_to_dashboard=AsyncMock(),
            send_to_client=AsyncMock(return_value=True),
            client_supports=Mock(return_value=True),
        )
        self.router = Router(self.manager)
        self.dashboard = object()
        self.payload = {
            "type": "backup_request",
            "request_id": str(uuid4()),
            "client_code": "CLIENT-1",
            "bo_connection_id": 2,
            "operation": "run",
            "parameters": {"settings": settings()},
        }

    async def asyncTearDown(self):
        self.router.discard_dashboard(self.dashboard)

    async def test_run_request_forwards_only_allowlisted_fields(self):
        await self.router.request(
            self.dashboard,
            {**self.payload, "sql": "DROP DATABASE x", "password": "secret"},
        )
        forwarded = self.manager.send_to_client.call_args.args[1]
        self.assertNotIn("sql", forwarded)
        self.assertNotIn("password", forwarded)
        self.assertEqual(forwarded["timeout"], 14500)

    async def test_unsupported_client_is_rejected_without_silent_wait(self):
        self.manager.client_supports.return_value = False
        await self.router.request(self.dashboard, self.payload)
        self.manager.send_to_client.assert_not_awaited()
        result = self.manager.send_to_dashboard.call_args.args[1]
        self.assertFalse(result["success"])
        self.assertIn("does not support", result["error"])

    async def test_executable_path_in_settings_is_rejected(self):
        malicious = settings()
        malicious["rclone_executable"] = r"C:\Windows\System32\cmd.exe"
        await self.router.request(
            self.dashboard,
            {**self.payload, "parameters": {"settings": malicious}},
        )
        self.manager.send_to_client.assert_not_awaited()
        self.assertFalse(self.manager.send_to_dashboard.call_args.args[1]["success"])

    async def test_result_returns_only_to_requesting_dashboard(self):
        await self.router.request(self.dashboard, self.payload)
        result = {
            "type": "backup_result",
            "request_id": self.payload["request_id"],
            "client_code": "CLIENT-1",
            "bo_connection_id": 2,
            "operation": "run",
            "success": True,
        }
        await self.router.result("CLIENT-1", result)
        self.manager.send_to_dashboard.assert_awaited_once_with(self.dashboard, result)
        self.assertFalse(self.router.pending)

    async def test_progress_is_forwarded_without_completing_request(self):
        await self.router.request(self.dashboard, self.payload)
        progress = {
            "type": "backup_progress",
            "request_id": self.payload["request_id"],
            "client_code": "CLIENT-1",
            "bo_connection_id": 2,
            "operation": "run",
            "stage": "backup",
            "message": "SQL Server backup progress: 45.0%",
            "percent": 45.0,
        }
        await self.router.progress("CLIENT-1", progress)
        forwarded = self.manager.send_to_dashboard.call_args.args[1]
        self.assertEqual(forwarded["percent"], 45.0)
        self.assertIn(self.payload["request_id"], self.router.pending)

    async def test_schedule_payload_is_strictly_validated(self):
        payload = {
            **self.payload,
            "operation": "save_schedule",
            "parameters": {"schedule": schedule(command="calc.exe")},
        }
        await self.router.request(self.dashboard, payload)
        self.manager.send_to_client.assert_not_awaited()


class BackupIntegrationSourceTests(unittest.TestCase):
    """Επιβεβαιώνει end-to-end wiring και απουσία cloud credentials από protocol."""

    def test_backup_protocol_is_connected_end_to_end(self):
        expected = {
            "client/app/client_agent.py": "_handle_backup_request",
            "server/app/routes/websocket_routes.py": "BackupRequestRouter",
            "dashboard/app/dashboard_app.py": "handle_backup_result",
            "dashboard/app/views/client_manage_window.py": "on_backup_request_callback",
            "dashboard/app/views/manage/database_tab.py": "BackupManagerWindow",
        }
        for path, marker in expected.items():
            with self.subTest(path=path):
                self.assertIn(marker, (ROOT / path).read_text(encoding="utf-8"))

    def test_client_advertises_backup_capability_and_window_has_watchdog(self):
        client_source = (ROOT / "client/app/client_agent.py").read_text(
            encoding="utf-8"
        )
        window_source = (ROOT / "dashboard/app/views/manage/backup_window.py").read_text(
            encoding="utf-8"
        )
        declarations = [node for node in ast.walk(ast.parse(client_source)) if isinstance(node, ast.Dict)]
        capabilities = next(ast.literal_eval(node.values[index])
                            for node in declarations for index, key in enumerate(node.keys)
                            if isinstance(key, ast.Constant) and key.value == "capabilities")
        self.assertIn("database_backup_v1", capabilities)
        self.assertIn("_handle_ack_timeout", window_source)
        self.assertIn("self.resizable(True, True)", window_source)
        self.assertNotIn("self.transient(parent)", window_source)

    def test_rclone_executable_cannot_be_received_from_dashboard(self):
        router_source = (ROOT / "server/app/websocket/backup_requests.py").read_text(
            encoding="utf-8"
        )
        settings_schema = router_source.split("SETTINGS_KEYS", 1)[1].split(")", 1)[0]
        self.assertNotIn("rclone_executable", settings_schema)

    def test_cli_entry_point_and_retention_choices_exist(self):
        main_source = (ROOT / "dashboard/app/main.py").read_text(encoding="utf-8")
        cli_source = (ROOT / "dashboard/app/backup_cli.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv[1] == "--backup"', main_source)
        for value in ("replace", "keep-all", "keep-last"):
            self.assertIn(f'"{value}"', cli_source)


if __name__ == "__main__":
    unittest.main()
