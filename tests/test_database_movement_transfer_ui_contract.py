from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "dashboard" / "app" / "views" / "manage" / "database_movement_transfer_tab.py"


class MovementTransferUiContractTests(unittest.TestCase):
    def test_card_and_three_modes_exist(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("Μεταφορά κινήσεων", source)
        self.assertIn("Εστιατορική ημερομηνία", source)
        self.assertIn("Πραγματική ημερομηνία", source)
        self.assertIn("Απόδειξη", source)

    def test_salesstation_is_optional_and_shared(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("Φίλτρο SalesStation", source)
        self.assertIn("use_station_var", source)
        self.assertIn("_selected_station_oid", source)

    def test_receipt_flow_searches_then_moves_selected_receipt(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("movement_receipt_search", source)
        self.assertIn("movement_transfer_receipt", source)
        self.assertIn("pos_hdr", source)
        self.assertIn("Current", source)
        self.assertIn("History", source)

    def test_real_mode_uses_old_real_and_new_dates(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("real_old_entry", source)
        self.assertIn("real_real_entry", source)
        self.assertIn("real_new_entry", source)


if __name__ == "__main__":
    unittest.main()
