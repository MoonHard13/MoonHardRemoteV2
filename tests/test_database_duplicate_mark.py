from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_APP = ROOT / "client" / "app"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if "app" not in sys.modules:
    app_package = types.ModuleType("app")
    app_package.__path__ = [str(CLIENT_APP)]
    sys.modules["app"] = app_package

_load_module(
    "app.database_maintenance_service",
    CLIENT_APP / "database_maintenance_service.py",
)
service_module = _load_module(
    "app.database_duplicate_mark_service",
    CLIENT_APP / "database_duplicate_mark_service.py",
)
DuplicateMarkDatabaseMaintenanceService = (
    service_module.DuplicateMarkDatabaseMaintenanceService
)


class FakeCursor:
    def __init__(self, fail_tokens: set[str] | None = None):
        self.fail_tokens = fail_tokens or set()
        self.executed: list[str] = []
        self.description = None
        self.messages = []
        self.rowcount = 1

    def execute(self, sql: str):
        self.executed.append(sql)
        for token in self.fail_tokens:
            if token in sql:
                raise RuntimeError(f"forced failure: {token}")
        self.rowcount = 1
        return self

    def nextset(self):
        return False

    def fetchmany(self, _size: int):
        return []


class DuplicateMarkServiceTests(unittest.TestCase):
    def _service_with_scripts(self, directory: Path):
        service = DuplicateMarkDatabaseMaintenanceService()
        service.SQL_DIR = directory
        (directory / service.SUCCESS_SCRIPT).write_text(
            "OPTIONAL_STEP_1;",
            encoding="utf-8",
        )
        (directory / service.MARK_SCRIPT).write_text(
            "MAIN_STEP_2_A;\nGO\nMAIN_STEP_2_B;",
            encoding="utf-8",
        )
        return service

    def test_optional_step_failure_does_not_stop_main_cleanup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service_with_scripts(Path(temp_dir))
            cursor = FakeCursor({"OPTIONAL_STEP_1"})
            progress: list[dict] = []

            result = service._execute_action(
                cursor,
                service.ACTION,
                {},
                "TestDb",
                progress.append,
            )

            self.assertFalse(result["success_step"]["success"])
            self.assertTrue(result["mark_step"]["success"])
            self.assertTrue(any("MAIN_STEP_2_A" in sql for sql in cursor.executed))
            self.assertTrue(any("MAIN_STEP_2_B" in sql for sql in cursor.executed))
            self.assertEqual(progress[-1]["percent"], 100)

    def test_required_step_failure_marks_action_failed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service_with_scripts(Path(temp_dir))
            cursor = FakeCursor({"MAIN_STEP_2_B"})

            result = service._execute_action(
                cursor,
                service.ACTION,
                {},
                "TestDb",
                None,
            )

            self.assertFalse(result["success"])
            self.assertTrue(result["success_step"]["success"])
            self.assertFalse(result["mark_step"]["success"])

    def test_go_separator_is_not_sent_to_odbc(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service_with_scripts(Path(temp_dir))
            cursor = FakeCursor()

            service._run_required_mark_step(cursor)

            main_batches = [sql for sql in cursor.executed if "MAIN_STEP_2" in sql]
            self.assertEqual(len(main_batches), 2)
            self.assertTrue(all("\nGO\n" not in sql.upper() for sql in main_batches))

    def test_action_is_allowlisted(self):
        self.assertIn(
            "delete_duplicate_mark",
            DuplicateMarkDatabaseMaintenanceService.ACTIONS,
        )


if __name__ == "__main__":
    unittest.main()
