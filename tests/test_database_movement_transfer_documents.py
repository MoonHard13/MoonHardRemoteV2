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
_load_module("app.database_movement_transfer_service", CLIENT_APP / "database_movement_transfer_service.py")
service_module = _load_module(
    "app.database_movement_transfer_documents_service",
    CLIENT_APP / "database_movement_transfer_documents_service.py",
)
MovementTransferDocumentsService = service_module.MovementTransferDocumentsService


class SearchStubService(MovementTransferDocumentsService):
    def _receipt_rows(self, _cursor, source, parameters):
        if source == "current":
            return [
                {
                    "source": "current",
                    "pos_hdr": 100,
                    "note_no": 10,
                    "note_code": 39,
                    "init_date": parameters["search_date"],
                    "real_date": parameters["search_date"],
                    "station_oid": 26,
                }
            ]
        return [
            {
                "source": "history",
                "pos_hdr": 200,
                "note_no": 9,
                "note_code": 39,
                "init_date": parameters["search_date"],
                "real_date": parameters["search_date"],
                "station_oid": 26,
            }
        ]


class MovementTransferDocumentSearchTests(unittest.TestCase):
    def setUp(self):
        self.service = MovementTransferDocumentsService()

    def test_document_number_is_optional_when_restaurant_date_is_present(self):
        validated = self.service._validate_parameters(
            "movement_receipt_search",
            {
                "note_no": "",
                "search_date": "20260929",
                "station_oid": "",
            },
        )
        self.assertIsNone(validated["note_no"])
        self.assertEqual(validated["search_date"], "20260929")
        self.assertIsNone(validated["station_oid"])

    def test_document_search_requires_number_or_date(self):
        with self.assertRaises(ValueError):
            self.service._validate_parameters(
                "movement_receipt_search",
                {"note_no": "", "search_date": "", "station_oid": ""},
            )

    def test_number_only_search_is_still_supported(self):
        validated = self.service._validate_parameters(
            "movement_receipt_search",
            {"note_no": "125", "search_date": "", "station_oid": "26"},
        )
        self.assertEqual(validated["note_no"], 125)
        self.assertEqual(validated["search_date"], "")
        self.assertEqual(validated["station_oid"], 26)

    def test_date_listing_can_include_current_and_history_documents(self):
        service = SearchStubService()
        result = service._search_receipts(
            object(),
            {"note_no": None, "search_date": "20260929", "station_oid": None},
        )
        self.assertEqual(len(result["receipts"]), 2)
        self.assertEqual({row["pos_hdr"] for row in result["receipts"]}, {100, 200})


if __name__ == "__main__":
    unittest.main()
