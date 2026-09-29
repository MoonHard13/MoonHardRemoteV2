from __future__ import annotations

import importlib.util
import sys
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

_load_module("app.database_maintenance_service", CLIENT_APP / "database_maintenance_service.py")
_load_module("app.database_duplicate_mark_service", CLIENT_APP / "database_duplicate_mark_service.py")
service_module = _load_module(
    "app.database_movement_transfer_service",
    CLIENT_APP / "database_movement_transfer_service.py",
)
MovementTransferDatabaseService = service_module.MovementTransferDatabaseService


class SourceCursor:
    def __init__(self):
        self.last_sql = ""
        self.executed: list[str] = []

    def execute(self, sql: str, *_params):
        self.last_sql = sql
        self.executed.append(sql)
        return self

    def fetchone(self):
        if "TblSnSalesTransHist" in self.last_sql:
            return (2,)
        return (0,)


class MovementTransferServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = MovementTransferDatabaseService()

    def test_actions_are_allowlisted(self):
        for action in (
            "movement_stations",
            "movement_receipt_search",
            "movement_transfer_date",
            "movement_transfer_receipt",
        ):
            self.assertIn(action, self.service.ACTIONS)

    def test_current_and_history_table_families_are_complete(self):
        self.assertEqual(
            self.service._tables("current"),
            (
                "TblSnSalesTrans",
                "TblSnSalesTransPos",
                "TblSnSalesPayWay",
                "TblSnSalesTransfers",
            ),
        )
        self.assertEqual(
            self.service._tables("history"),
            (
                "TblSnSalesTransHist",
                "TblSnSalesTransPosHist",
                "TblSnSalesPayWayHist",
                "TblSnSalesTransfersHist",
            ),
        )

    def test_rest_date_mode_accepts_optional_station(self):
        validated = self.service._validate_parameters(
            "movement_transfer_date",
            {
                "mode": "rest",
                "old_date": "20260928",
                "real_date": "",
                "new_date": "20260929",
                "station_oid": "",
            },
        )
        self.assertEqual(validated["mode"], "rest")
        self.assertIsNone(validated["station_oid"])

    def test_real_date_mode_keeps_old_real_and_new_dates(self):
        validated = self.service._validate_parameters(
            "movement_transfer_date",
            {
                "mode": "real",
                "old_date": "20260928",
                "real_date": "20260929",
                "new_date": "20260930",
                "station_oid": "26",
            },
        )
        self.assertEqual(validated["real_date"], "20260929")
        self.assertEqual(validated["station_oid"], 26)

    def test_date_source_falls_back_to_history_only_when_current_is_empty(self):
        cursor = SourceCursor()
        source = self.service._resolve_date_source(
            cursor,
            {
                "mode": "rest",
                "old_date": "20260701",
                "real_date": "",
                "new_date": "20260702",
                "station_oid": None,
            },
        )
        self.assertEqual(source, "history")
        self.assertIn("TblSnSalesTrans", cursor.executed[0])
        self.assertIn("TblSnSalesTransHist", cursor.executed[1])

    def test_receipt_transfer_uses_pos_header_as_identity(self):
        validated = self.service._validate_parameters(
            "movement_transfer_receipt",
            {
                "source": "history",
                "pos_hdr": "4826511",
                "note_no": "14",
                "note_code": "39",
                "old_date": "20260929",
                "new_date": "20260930",
                "station_oid": "26",
            },
        )
        self.assertEqual(validated["pos_hdr"], 4826511)
        self.assertEqual(validated["source"], "history")


if __name__ == "__main__":
    unittest.main()
