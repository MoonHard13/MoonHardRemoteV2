"""Δοκιμές για το ανασχεδιασμένο Bulk Update Progress window."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))


class BulkUpdateProgressSourceTests(unittest.TestCase):
    """Ελέγχει τη δομή του νέου UI χωρίς γραφικό περιβάλλον."""

    def test_bulk_update_uses_single_tree_instead_of_client_cards(self):
        """Η μεγάλη λίστα αποδίδεται από ένα Treeview."""

        source = (
            PROJECT_ROOT / "dashboard/app/views/bulk_update_progress_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.client_tree = ttk.Treeview", source)
        self.assertNotIn("self.scroll_frame = ctk.CTkScrollableFrame", source)
        self.assertIn("self.row_snapshots", source)

    def test_bulk_update_has_progress_filters_and_shortcuts(self):
        """Το UI διαθέτει progress, φίλτρα και shortcuts."""

        source = (
            PROJECT_ROOT / "dashboard/app/views/bulk_update_progress_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.progress_bar = ctk.CTkProgressBar", source)
        self.assertIn('"Problems"', source)
        self.assertIn('self.bind("<Control-r>"', source)
        self.assertIn('self.bind("<Control-f>"', source)
        self.assertIn('self.bind("<Control-l>"', source)
        self.assertIn('self.bind("<Escape>"', source)

    @unittest.skipUnless(
        importlib.util.find_spec("customtkinter"),
        "Απαιτεί CustomTkinter.",
    )
    def test_stage_groups_and_summary_remain_consistent(self):
        """Τα internal stages ομαδοποιούνται σωστά χωρίς Tk window."""

        from app.views.bulk_update_progress_window import BulkUpdateProgressWindow

        window = object.__new__(BulkUpdateProgressWindow)
        self.assertTrue(window._stage_matches_filter("failed", "Problems"))
        self.assertTrue(window._stage_matches_filter("downloading", "In progress"))
        self.assertFalse(window._stage_matches_filter("up_to_date", "Completed"))
        summary = window._build_summary_text(
            {
                "completed": 2,
                "up_to_date": 3,
                "downloading": 2,
                "queued": 4,
                "failed": 1,
            }
        )
        self.assertIn("Finished: 5", summary)
        self.assertIn("In progress: 2", summary)
        self.assertIn("Problems: 1", summary)


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class BulkUpdateProgressUITests(unittest.TestCase):
    """Ελέγχει πραγματικά widgets και ενημερώσεις κατάστασης."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.bulk_update_progress_window import BulkUpdateProgressWindow

        self.root = ctk.CTk()
        self.root.geometry("1600x900")
        self.retry_callback = Mock()
        self.window = BulkUpdateProgressWindow(
            self.root,
            on_retry_callback=self.retry_callback
        )
        self.window.geometry("1400x820")
        self.clients = [
            {
                "client_code": f"CLIENT-{index}",
                "display_name": f"CLIENT {index}",
                "pc_name": f"PC-{index}",
                "app_version": "1.0.13"
            }
            for index in range(1, 5)
        ]
        self.window.initialize_clients(self.clients)
        self.root.update()

    def tearDown(self):
        if self.window.winfo_exists():
            self.window.destroy()
        self.root.destroy()

    def test_metrics_and_progress_follow_client_states(self):
        """Τα counters και το progress υπολογίζονται σωστά."""

        states = {
            "CLIENT-1": {"stage": "completed", "latest_version": "1.0.14"},
            "CLIENT-2": {"stage": "up_to_date", "latest_version": "1.0.13"},
            "CLIENT-3": {"stage": "downloading", "latest_version": "1.0.14"},
            "CLIENT-4": {
                "stage": "failed",
                "latest_version": "1.0.14",
                "retry_count": 1,
                "error": "Download failed"
            }
        }
        self.window.update_states(states)
        self.root.update()

        self.assertEqual(self.window.metric_values["total"].cget("text"), "4")
        self.assertEqual(self.window.metric_values["finished"].cget("text"), "2")
        self.assertEqual(self.window.metric_values["active"].cget("text"), "1")
        self.assertEqual(self.window.metric_values["problems"].cget("text"), "1")
        self.assertEqual(self.window.progress_label.cget("text"), "75%")
        self.assertEqual(self.window.retry_button.cget("state"), "normal")
        self.assertEqual(len(self.window.client_tree.get_children("")), 4)

    def test_problem_filter_and_selection_details(self):
        """Το Problems filter και το details panel δείχνουν το σωστό client."""

        states = {
            "CLIENT-1": {"stage": "completed"},
            "CLIENT-2": {"stage": "up_to_date"},
            "CLIENT-3": {"stage": "checking"},
            "CLIENT-4": {
                "stage": "failed",
                "retry_count": 2,
                "error": "Checksum mismatch"
            }
        }
        self.window.update_states(states)
        self.window.status_filter.set("Problems")
        self.window._apply_filters()
        self.root.update()

        self.assertEqual(
            self.window.client_tree.get_children(""),
            ("CLIENT-4",)
        )
        self.window.client_tree.selection_set("CLIENT-4")
        self.window._show_selected_details()
        self.assertEqual(
            self.window.detail_status_label.cget("text"),
            "FAILED"
        )
        self.assertIn(
            "Checksum mismatch",
            self.window.detail_text_label.cget("text")
        )

    def test_retry_action_calls_existing_callback(self):
        """Το νέο κουμπί διατηρεί το υπάρχον retry callback."""

        self.window._retry_clicked()
        self.retry_callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
