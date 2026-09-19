"""Δοκιμές της responsive διεπαφής Provider και Διαβιβασμένων."""

import ast
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))


class ProviderScrollbarSourceTests(unittest.TestCase):
    """Ελέγχει τη συμβατότητα των scrollbars χωρίς να απαιτεί γραφικό περιβάλλον."""

    def test_customtkinter_scrollbars_use_orientation_argument(self):
        """Το CTkScrollbar δέχεται orientation και όχι το ttk όρισμα orient."""

        project_root = Path(__file__).resolve().parents[1]
        source_files = (
            project_root / "dashboard/app/views/manage/provider_tab.py",
            project_root / "dashboard/app/views/manage/provider_transmitted_window.py",
        )
        scrollbar_calls = []
        for source_file in source_files:
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            scrollbar_calls.extend(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "CTkScrollbar"
            )

        self.assertEqual(len(scrollbar_calls), 8)
        for call in scrollbar_calls:
            keywords = {keyword.arg for keyword in call.keywords}
            self.assertIn("orientation", keywords)
            self.assertNotIn("orient", keywords)


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class ProviderUITests(unittest.TestCase):
    """Ελέγχει πραγματικά widgets χωρίς Client, SQL Server ή Provider API."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.provider_tab import ProviderTab

        self.root = ctk.CTk()
        self.root.geometry("1600x900")
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.requests = Mock()
        self.tab = ProviderTab(
            self.root,
            client_code="CLIENT-TEST",
            get_bo_values_callback=lambda: [
                "ID 1 - InitialTest",
                "ID 3 - IthakiTest",
            ],
            get_selected_bo_id_callback=lambda: 1,
            on_provider_request_callback=self.requests,
        )
        self.tab.grid(row=0, column=0, sticky="nsew")
        self.tab.update_bo_values(
            ["ID 1 - InitialTest", "ID 3 - IthakiTest"],
            "ID 1 - InitialTest",
        )
        self.root.update()
        self.tab._apply_layout()
        self.root.update()

    def tearDown(self):
        if self.tab.winfo_exists():
            self.tab.destroy()
        for job in self.root.tk.call("after", "info"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.root.destroy()

    def _open_transmitted(self):
        self.tab._open_transmitted()
        self.root.update()
        view = self.tab.transmitted_view
        if view._initial_load_after_id is not None:
            view.after_cancel(view._initial_load_after_id)
            view._initial_load_after_id = None
        view._apply_layout()
        self.root.update()
        return view

    def test_provider_workspace_has_clear_hierarchy_and_wide_filters(self):
        """Header, filters, results και actions έχουν σαφή οπτική ιεραρχία."""

        from app.ui.theme import COLORS

        self.assertEqual(self.tab.provider_connection_badge.cget("text"), "BOConnection 1")
        self.assertTrue(self.tab._wide_layout)
        self.assertEqual(len(self.tab.provider_filter_frames), 4)
        self.assertEqual(
            [int(frame.grid_info()["column"]) for frame in self.tab.provider_filter_frames],
            [0, 1, 2, 3],
        )
        self.assertGreater(self.tab.provider_tree.winfo_height(), 250)
        self.assertEqual(self.tab.mydata_button.cget("fg_color"), COLORS.danger_soft)
        self.assertEqual(self.tab.mydata_button.cget("border_color"), COLORS.danger)

    def test_compact_provider_layout_uses_two_filter_columns(self):
        """Σε μικρό πλάτος τα φίλτρα γίνονται δύο σειρές χωρίς clipping."""

        self.root.geometry("980x760")
        self.root.update()
        self.tab._apply_layout()
        self.assertFalse(self.tab._wide_layout)
        positions = [
            (int(frame.grid_info()["row"]), int(frame.grid_info()["column"]))
            for frame in self.tab.provider_filter_frames
        ]
        self.assertEqual(positions, [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(int(self.tab.payways_button.grid_info()["row"]), 1)
        self.assertEqual(int(self.tab.mydata_button.grid_info()["row"]), 1)

    def test_provider_search_payload_and_status_contract_are_preserved(self):
        """Το νέο UI διατηρεί ακριβώς το υπάρχον request contract."""

        from app.ui.theme import COLORS

        self.tab.provider_afm_entry.insert(0, "123456789")
        self.tab.provider_invoice_type_entry.insert(0, "1.1")
        self.tab._search_invoices()
        payload = self.requests.call_args.args[0]
        self.assertEqual(payload["type"], "provider_search_invoices")
        self.assertEqual(payload["client_code"], "CLIENT-TEST")
        self.assertEqual(payload["bo_connection_id"], 1)
        self.assertEqual(payload["afm"], "123456789")
        self.assertEqual(payload["invoice_type"], "1.1")
        self.assertEqual(self.tab.provider_status_label.cget("fg_color"), COLORS.info_soft)

    def test_transmitted_layout_switches_between_three_and_two_columns(self):
        """Τα φίλτρα Διαβιβασμένων προσαρμόζονται στο διαθέσιμο πλάτος."""

        view = self._open_transmitted()
        self.assertTrue(view._wide_layout)
        self.assertEqual(len(view._filter_frames), 5)
        self.assertEqual(int(view._filter_frames[2].grid_info()["column"]), 2)

        self.root.geometry("980x760")
        self.root.update()
        view._apply_layout()
        self.assertFalse(view._wide_layout)
        self.assertEqual(int(view._filter_frames[2].grid_info()["row"]), 1)
        self.assertEqual(int(view._filter_frames[2].grid_info()["column"]), 0)

    def test_transmitted_results_url_actions_and_status_pill(self):
        """Results count, URL selection και clipboard actions λειτουργούν μαζί."""

        from app.ui.theme import COLORS

        view = self._open_transmitted()
        request_id = "ui-result"
        timer = view.after(100000, lambda: None)
        view.pending[request_id] = ("provider_transmitted_search", timer)
        url = "https://example.invalid/invoice?id=123"
        view.handle_result(
            {
                "request_id": request_id,
                "type": "provider_transmitted_search_result",
                "client_code": "CLIENT-TEST",
                "bo_connection_id": 1,
                "success": True,
                "has_more": False,
                "invoices": [
                    {
                        "ResponseOID": 10,
                        "InvoiceDate": "2026-09-19",
                        "DocumentType": "Απόδειξη",
                        "Series": "Α",
                        "Number": "123",
                        "MARK": "400001",
                        "DocumentURL": url,
                    }
                ],
            }
        )
        self.assertEqual(view.result_count_label.cget("text"), "1 εγγραφές")
        self.assertEqual(view.status.cget("fg_color"), COLORS.success_soft)
        view.tree.selection_set("10")
        view._selection_changed()
        self.assertEqual(view.url_text.get(), url)
        self.assertEqual(view.open_button.cget("state"), "normal")
        view.copy_url()
        self.assertEqual(view.clipboard_get(), url)


if __name__ == "__main__":
    unittest.main()
