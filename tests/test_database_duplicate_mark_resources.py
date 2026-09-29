from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "client" / "app" / "sql"


class DuplicateMarkResourceTests(unittest.TestCase):
    def test_success_script_is_present(self):
        path = SQL_DIR / "!Delete_Duplicate_Success_Mark.sql"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("#Conflicts", text)
        self.assertIn("MyDATA_ResponseCancellationMARK", text)

    def test_main_script_is_present_and_has_two_batches(self):
        path = SQL_DIR / "!Delete_Duplicate_MArK.sql"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("DuplicateMArK", text)
        self.assertGreaterEqual(text.lower().count("\ngo\n"), 2)


if __name__ == "__main__":
    unittest.main()
