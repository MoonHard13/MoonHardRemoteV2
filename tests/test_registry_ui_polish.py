from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = ROOT / "dashboard"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from app.views.manage.registry_polished_navigation import PolishedRegistryTab  # noqa: E402


class RegistryUiPolishTests(unittest.TestCase):
    def test_delete_parent_scope(self) -> None:
        parent = PolishedRegistryTab._parent_scope(
            {
                "hive": "HKLM",
                "path": r"SOFTWARE\Vendor\Product",
                "view": "64",
            }
        )
        self.assertEqual(
            parent,
            {"hive": "HKLM", "path": r"SOFTWARE\Vendor", "view": "64"},
        )

    def test_delete_parent_scope_for_top_level_key(self) -> None:
        parent = PolishedRegistryTab._parent_scope(
            {"hive": "HKCU", "path": "Software", "view": "default"}
        )
        self.assertEqual(
            parent,
            {"hive": "HKCU", "path": "", "view": "default"},
        )

    def test_context_menu_action_contracts(self) -> None:
        for label in (
            "New Key",
            "New Value",
            "Create Snapshot",
            "Export",
            "Add to Favorites",
            "Open Favorites",
            "Copy Key Name",
        ):
            self.assertIn(label, PolishedRegistryTab.KEY_CONTEXT_ACTIONS)

        for label in (
            "Modify",
            "Delete",
            "Copy Name",
            "Copy Data",
            "Create Profile from Value",
        ):
            self.assertIn(label, PolishedRegistryTab.VALUE_CONTEXT_ACTIONS)

    def test_polish_navigation_and_import_contract(self) -> None:
        for method_name in (
            "_on_view_changed",
            "navigate_address",
            "go_back",
            "show_favorites",
            "open_import_dialog",
            "_show_key_context_menu",
            "_show_value_context_menu",
            "_continue_tree_navigation",
        ):
            self.assertTrue(callable(getattr(PolishedRegistryTab, method_name, None)))
        self.assertIn("_continue_tree_navigation", PolishedRegistryTab.__dict__)

    def test_read_reg_file_utf16(self) -> None:
        text = "Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\MoonHard]\r\n\"Test\"=\"OK\"\r\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.reg"
            path.write_bytes(text.encode("utf-16"))
            self.assertEqual(PolishedRegistryTab._read_reg_text_file(path), text)

    def test_read_reg_file_utf8_bom(self) -> None:
        text = "Windows Registry Editor Version 5.00\n[HKEY_CURRENT_USER\\Software\\MoonHard]\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.reg"
            path.write_bytes(text.encode("utf-8-sig"))
            self.assertEqual(PolishedRegistryTab._read_reg_text_file(path), text)


if __name__ == "__main__":
    unittest.main()
