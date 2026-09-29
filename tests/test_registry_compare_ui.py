"""Headless tests for Registry Compare diff semantics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = ROOT / "dashboard"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from app.views.manage.registry_compare_center import RegistryCompareTab  # noqa: E402


class RegistryCompareUiTests(unittest.TestCase):
    def test_compare_modes_are_available(self) -> None:
        self.assertEqual(
            RegistryCompareTab.MODES,
            ("Current vs Snapshot", "Current vs Profile", "PC vs PC"),
        )

    def test_pc_compare_classifies_same_different_missing_and_extra(self) -> None:
        left = {
            "exists": True,
            "path": r"SOFTWARE\MoonHard",
            "tree": {
                "values": [
                    {"name": "Mode", "type": "REG_SZ", "data": "A"},
                    {"name": "OnlyLeft", "type": "REG_DWORD", "data": 1},
                ],
                "subkeys": {
                    "Child": {
                        "values": [
                            {"name": "Same", "type": "REG_SZ", "data": "OK"},
                        ],
                        "subkeys": {},
                    }
                },
            },
        }
        right = {
            "exists": True,
            "path": r"SOFTWARE\MoonHard",
            "tree": {
                "values": [
                    {"name": "Mode", "type": "REG_SZ", "data": "B"},
                    {"name": "OnlyRight", "type": "REG_DWORD", "data": 2},
                ],
                "subkeys": {
                    "Child": {
                        "values": [
                            {"name": "Same", "type": "REG_SZ", "data": "OK"},
                        ],
                        "subkeys": {},
                    }
                },
            },
        }

        results, summary = RegistryCompareTab.compare_capture_payloads(left, right)
        self.assertEqual(summary["different"], 1)
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(summary["extra"], 1)
        self.assertEqual(summary["same"], 3)  # root key, child key, shared value
        statuses = {row["status"] for row in results}
        self.assertEqual(statuses, {"Same", "Different", "Missing", "Extra"})

    def test_missing_target_scope_marks_source_as_missing(self) -> None:
        left = {
            "exists": True,
            "path": r"SOFTWARE\MoonHard",
            "tree": {
                "values": [{"name": "Mode", "type": "REG_SZ", "data": "A"}],
                "subkeys": {},
            },
        }
        right = {
            "exists": False,
            "path": r"SOFTWARE\MoonHard",
            "tree": {"values": [], "subkeys": {}},
        }
        _results, summary = RegistryCompareTab.compare_capture_payloads(left, right)
        self.assertEqual(summary["missing"], 2)  # root key + value
        self.assertEqual(summary["same"], 0)
        self.assertEqual(summary["different"], 0)
        self.assertEqual(summary["extra"], 0)

    def test_binary_compare_display_does_not_expose_base64_blob(self) -> None:
        text = RegistryCompareTab._display_compare_value(
            {
                "type": "REG_BINARY",
                "data": {"encoding": "base64", "value": "AAECAw==", "length": 4},
            }
        )
        self.assertEqual(text, "REG_BINARY: <binary 4 bytes>")

    def test_export_rows_strip_raw_registry_payloads(self) -> None:
        rows = [
            {
                "status": "Different",
                "kind": "Value",
                "path": r"SOFTWARE\MoonHard",
                "name": "Blob",
                "left": "REG_BINARY: <binary 4 bytes>",
                "right": "REG_BINARY: <binary 4 bytes>",
                "left_raw": {"type": "REG_BINARY", "data": {"value": "SECRET_BASE64"}},
                "right_raw": {"type": "REG_BINARY", "data": {"value": "OTHER_SECRET"}},
            }
        ]
        public_rows = RegistryCompareTab._public_compare_rows(rows)
        self.assertEqual(
            set(public_rows[0]),
            {"status", "kind", "path", "name", "left", "right"},
        )
        self.assertNotIn("SECRET_BASE64", str(public_rows))
        self.assertNotIn("OTHER_SECRET", str(public_rows))


if __name__ == "__main__":
    unittest.main()
