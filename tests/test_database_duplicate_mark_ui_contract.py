from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "dashboard" / "app" / "views" / "manage" / "database_duplicate_mark_tab.py"


class DuplicateMarkUiContractTests(unittest.TestCase):
    def test_database_button_and_action_name_exist(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("Διαγραφή διπλών ΜΑΡΚ", source)
        self.assertIn('"delete_duplicate_mark"', source)
        self.assertIn("request_delete_duplicate_mark", source)

    def test_mark_cleanup_uses_its_own_card(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn('"MARK cleanup"', source)
        self.assertIn("self.mark_cleanup_card", source)
        self.assertIn("self.right_stack", source)
        self.assertNotIn("self._action_button(\n            self.maintenance_card,\n            text=\"Διαγραφή διπλών ΜΑΡΚ\"", source)

    def test_optional_step_is_described_as_best_effort(self):
        source = UI_FILE.read_text(encoding="utf-8")
        self.assertIn("best effort", source)
        self.assertIn("warning", source.lower())
        self.assertIn("η διαδικασία θα συνεχίσει", source)


if __name__ == "__main__":
    unittest.main()
