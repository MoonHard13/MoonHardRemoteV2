"""Δοκιμές της responsive διεπαφής του Database tab."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class DatabaseUITests(unittest.TestCase):
    """Ελέγχει πραγματικά widgets χωρίς σύνδεση σε Client ή SQL Server."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.database_tab import DatabaseTab

        self.root = ctk.CTk()
        self.root.geometry("1800x950")
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.request = Mock()
        self.tab = DatabaseTab(
            self.root,
            client_code="CLIENT-TEST",
            get_bo_values_callback=lambda: ["ID 1 - InitialTest"],
            get_selected_bo_id_callback=lambda: 1,
            on_database_request_callback=self.request,
        )
        self.tab.grid(sticky="nsew")
        self.root.update()
        self.tab._apply_layout()
        self.root.update()

    def tearDown(self):
        self.tab.destroy()
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.root.destroy()

    def test_wide_workspace_keeps_activity_visible(self):
        """Στο μεγάλο παράθυρο οι λειτουργίες και το Activity μένουν δίπλα."""

        self.assertEqual(int(self.tab.operations.grid_info()["column"]), 0)
        self.assertEqual(int(self.tab.output_card.grid_info()["column"]), 1)
        self.assertEqual(int(self.tab.output_card.grid_info()["row"]), 0)
        self.assertEqual(int(self.tab.right_stack.grid_info()["column"]), 1)
        self.assertGreater(self.tab.output_box.winfo_height(), 300)

    def test_small_workspace_stacks_activity_and_cards(self):
        """Στο μικρό παράθυρο δεν υπάρχει οριζόντια αποκοπή των cards."""

        self.root.geometry("900x700")
        self.root.update()
        self.tab._apply_layout()
        self.root.update()
        self.assertEqual(int(self.tab.output_card.grid_info()["column"]), 0)
        self.assertEqual(int(self.tab.output_card.grid_info()["row"]), 1)
        self.assertEqual(int(self.tab.right_stack.grid_info()["column"]), 0)
        self.assertEqual(int(self.tab.right_stack.grid_info()["row"]), 1)

    def test_actions_payload_copy_clear_and_busy_state(self):
        """Το νέο UI διατηρεί το request contract και το read-only Activity."""

        self.tab.request_action("sales_trans_info")
        payload = self.request.call_args.args[0]
        self.assertEqual(payload["client_code"], "CLIENT-TEST")
        self.assertEqual(payload["bo_connection_id"], 1)
        self.assertEqual(payload["action"], "sales_trans_info")
        self.assertTrue(all(button.cget("state") == "disabled"
                            for button in self.tab.action_buttons))
        self.tab.copy_output()
        self.assertIn("SalesTrans", self.root.clipboard_get())
        self.tab.clear_output()
        self.assertEqual(self.tab.output_box.get("1.0", "end-1c"),
                         "No activity to display.")

    def test_connection_badge_and_destructive_visual_hierarchy(self):
        """Η επιλογή βάσης και τα destructive actions ξεχωρίζουν καθαρά."""

        from app.ui.theme import COLORS

        self.assertEqual(self.tab.selection_badge.cget("text"), "Database selected")
        self.assertEqual(self.tab.selection_badge.cget("fg_color"), COLORS.success_soft)
        for button in (self.tab.clean_button, self.tab.shrink_button,
                       self.tab.rebuild_button):
            self.assertEqual(button.cget("fg_color"), COLORS.danger_soft)
            self.assertEqual(button.cget("border_color"), COLORS.danger)


if __name__ == "__main__":
    unittest.main()
