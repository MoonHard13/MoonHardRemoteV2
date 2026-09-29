from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_UI = ROOT / "dashboard" / "app" / "views" / "manage" / "database_movement_transfer_documents_tab.py"
WIDE_UI = ROOT / "dashboard" / "app" / "views" / "manage" / "database_movement_transfer_wide_tab.py"
EXTENSION = ROOT / "dashboard" / "app" / "database_movement_transfer_extension.py"


class MovementTransferDocumentsUiTests(unittest.TestCase):
    def test_user_facing_terms_use_documents(self):
        source = DOCUMENT_UI.read_text(encoding="utf-8")
        self.assertIn('RECEIPT_MODE = "Παραστατικό"', source)
        self.assertIn("Αρ. παραστατικού", source)
        self.assertIn("Αναζήτηση παραστατικών", source)
        self.assertIn("Μεταφορά επιλεγμένων παραστατικών", source)
        self.assertNotIn('RECEIPT_MODE = "Απόδειξη"', source)
        self.assertNotIn('text="Αναζήτηση απόδειξης"', source)
        self.assertNotIn('text="Μεταφορά επιλεγμένης απόδειξης"', source)

    def test_date_results_show_both_restaurant_and_real_dates(self):
        source = DOCUMENT_UI.read_text(encoding="utf-8")
        self.assertIn('"Εστιατορική"', source)
        self.assertIn('"Πραγματική"', source)
        self.assertIn('document.get("init_date")', source)
        self.assertIn('document.get("real_date")', source)

    def test_documents_are_multi_selectable(self):
        source = DOCUMENT_UI.read_text(encoding="utf-8")
        self.assertIn("CTkCheckBox", source)
        self.assertIn("Επιλογή όλων", source)
        self.assertIn("Καθαρισμός", source)
        self.assertIn("_selected_documents", source)

    def test_current_history_is_not_shown_in_document_rows(self):
        source = DOCUMENT_UI.read_text(encoding="utf-8")
        self.assertNotIn('source_label = "Current"', source)
        self.assertNotIn('else "History"', source)

    def test_only_movement_feature_spans_two_columns(self):
        source = WIDE_UI.read_text(encoding="utf-8")
        self.assertIn('if title == "Μεταφορά κινήσεων"', source)
        self.assertIn("parent = self.operations", source)
        self.assertIn("self.movement_card.grid_configure", source)
        self.assertIn("columnspan=2", source)
        self.assertNotIn("in_=self.left_stack", source)
        self.assertNotIn("self.right_stack.grid_forget()", source)

    def test_document_description_is_before_document_number(self):
        source = WIDE_UI.read_text(encoding="utf-8")
        self.assertIn('"Περιγραφή παραστατικού",\n            "Αρ. παραστατικού"', source)
        self.assertIn('document.get("document_descr")', source)

    def test_extension_uses_wide_document_tab(self):
        source = EXTENSION.read_text(encoding="utf-8")
        self.assertIn("MovementTransferWideDocumentsTab", source)


if __name__ == "__main__":
    unittest.main()
