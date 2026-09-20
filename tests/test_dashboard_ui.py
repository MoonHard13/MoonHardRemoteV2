"""Δοκιμές του responsive dashboard workspace και του νέου branding."""

import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))


class DashboardSourceTests(unittest.TestCase):
    """Ελέγχει branding και presentation helpers χωρίς γραφικό περιβάλλον."""

    def test_visible_branding_no_longer_contains_v2(self):
        """Τα εμφανιζόμενα ονόματα προϊόντος δεν περιέχουν πλέον το v2."""

        source_files = (
            PROJECT_ROOT / "dashboard/app/config.py",
            PROJECT_ROOT / "client/app/config.py",
            PROJECT_ROOT / "client/app/main.py",
            PROJECT_ROOT / "server/app/config.py",
            PROJECT_ROOT / "server/render.yaml",
            PROJECT_ROOT / "installer/client_files/MoonHardRemoteClientService.xml",
        )
        for source_file in source_files:
            content = source_file.read_text(encoding="utf-8").lower()
            self.assertNotIn("moonhard remote v2", content)

    def test_dashboard_hero_header_is_removed(self):
        """Η αρχική οθόνη περιέχει μόνο το client workspace."""

        source = (PROJECT_ROOT / "dashboard/app/dashboard_app.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("self.header_frame", source)
        self.assertNotIn("Remote client control dashboard", source)
        self.assertIn("self.grid_rowconfigure(0, weight=1)", source)

    def test_customtkinter_place_uses_constructor_dimensions(self):
        """Το CTk place δεν δέχεται width/height όπως το tkinter place."""

        source = (PROJECT_ROOT / "dashboard/app/views/clients_view.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("status_text = tk.Label", source)
        self.assertIn(
            "status_text.place(x=0, y=0, width=258, height=28)", source
        )
        self.assertIn("buttons_frame.place(x=0, y=38)", source)
        self.assertNotIn("buttons_frame.place(x=0, y=38, width=", source)

    def test_filter_change_forces_clean_paginated_render(self):
        """Η αλλαγή φίλτρου ξεκινά καθαρά από την πρώτη σελίδα."""

        source = (PROJECT_ROOT / "dashboard/app/views/clients_view.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("self.page_size: int = 25", source)
        self.assertIn("if filters_changed:\n            self.current_page = 0", source)
        self.assertIn(
            "self._render_clients(page_clients, len(filtered_clients))",
            source,
        )

    @unittest.skipUnless(
        importlib.util.find_spec("customtkinter"),
        "Απαιτεί CustomTkinter.",
    )
    def test_client_presentation_keeps_all_operational_fields(self):
        """Η compact κάρτα διατηρεί εκδόσεις, code και last-seen."""

        from app.views.clients_view import ClientsView

        values = ClientsView._client_presentation(
            {
                "display_name": "TEST CLIENT",
                "pc_name": "TEST-PC",
                "username": "user",
                "client_code": "CLIENT-123",
                "group_name": "Athens",
                "app_version": "1.0.13",
                "amv_version": "13.30.000",
                "bo_version": "13.30.001",
                "etp_version": "4.1.0.1",
                "aws_version": "7.6.0.0",
                "last_seen": "2026-09-19T15:00:00+00:00",
            }
        )
        self.assertEqual(values["name"], "TEST CLIENT")
        self.assertEqual(values["group"], "Athens")
        self.assertIn("TEST-PC", values["identity"])
        self.assertIn("13.30.000", values["versions"])
        self.assertIn("CLIENT-123", values["meta"])
        self.assertIn("2026-09-19", values["meta"])


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class DashboardUITests(unittest.TestCase):
    """Ελέγχει πραγματικά dashboard widgets χωρίς WebSocket σύνδεση."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.clients_view import ClientsView

        self.root = ctk.CTk()
        self.root.geometry("1600x900")
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.refresh = Mock()
        self.view = ClientsView(
            self.root,
            on_manage_callback=Mock(),
            on_delete_callback=Mock(),
            on_refresh_callback=self.refresh,
            on_bulk_update_callback=Mock(),
            on_group_callback=Mock(),
        )
        self.view.grid(row=0, column=0, sticky="nsew")
        self.root.update()
        self.view._apply_layout()
        self.view.update_clients(
            [
                {
                    "display_name": "TEST CLIENT",
                    "pc_name": "TEST-PC",
                    "username": "user",
                    "client_code": "CLIENT-123",
                    "status": "online",
                    "ws_connected": True,
                    "group_name": "Athens",
                    "app_version": "1.0.13",
                    "amv_version": "13.30.000",
                    "bo_version": "13.30.001",
                    "etp_version": "4.1.0.1",
                    "aws_version": "7.6.0.0",
                    "last_seen": "2026-09-19T15:00:00+00:00",
                }
            ],
            force=True,
        )
        self.root.update()

    def tearDown(self):
        if self.view.winfo_exists():
            self.view.destroy()
        for job in self.root.tk.call("after", "info"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.root.destroy()

    def test_workspace_metrics_and_client_hierarchy(self):
        """Counters, status badge και client fields ενημερώνονται σωστά."""

        from app.ui.theme import COLORS

        self.assertEqual(self.view.count_label.cget("text"), "1 / 1 shown")
        self.assertEqual(self.view.online_count_label.cget("text"), "1 online")
        self.assertEqual(
            self.view.connected_count_label.cget("text"), "1 controllable"
        )
        row = self.view.client_rows["CLIENT-123"]
        self.assertEqual(row["name_label"].cget("text"), "TEST CLIENT")
        self.assertEqual(row["group_label"].cget("text"), "Athens")
        self.assertEqual(row["status_text"].cget("text"), "ONLINE  ·  CONNECTED")
        self.assertEqual(row["status_label"].cget("background"), COLORS.success)
        self.assertEqual(row["status_text"].cget("background"), COLORS.success_soft)
        self.assertTrue(row["status_label"].grid_info())
        self.assertEqual(row["status_text"].winfo_manager(), "place")
        self.assertEqual(row["buttons_frame"].winfo_manager(), "place")
        self.assertEqual(int(row["status_text"].place_info()["y"]), 0)
        self.assertEqual(int(row["buttons_frame"].place_info()["y"]), 38)

    def test_grouped_offline_client_keeps_red_status_markers(self):
        """Group badge και scroll position δεν κρύβουν το offline styling."""

        from app.ui.theme import COLORS

        self.view.update_clients(
            [
                {
                    "display_name": "GROUPED CLIENT",
                    "pc_name": "GROUPED-PC",
                    "username": "user",
                    "client_code": "CLIENT-GROUPED",
                    "status": "offline",
                    "ws_connected": False,
                    "group_name": "KASTELORIZO",
                    "app_version": "1.0.13",
                }
            ],
            force=True,
        )
        self.root.update()

        row = self.view.client_rows["CLIENT-GROUPED"]
        self.assertEqual(row["status_label"].cget("background"), COLORS.danger)
        self.assertEqual(row["status_text"].cget("background"), COLORS.danger_soft)
        self.assertEqual(row["status_text"].cget("text"), "OFFLINE")
        self.assertEqual(row["status_text"].cget("foreground"), COLORS.danger)
        self.assertEqual(row["group_label"].cget("text"), "KASTELORIZO")
        self.assertTrue(row["status_label"].grid_info())
        self.assertEqual(row["status_text"].winfo_manager(), "place")
        self.assertEqual(row["buttons_frame"].winfo_manager(), "place")

    def test_selecting_group_recreates_visible_online_and_offline_rows(self):
        """Το group filter εμφανίζει σωστά και τις δύο καταστάσεις."""

        from app.ui.theme import COLORS

        grouped_clients = [
            {
                "display_name": "GROUPED ONLINE",
                "pc_name": "ONLINE-PC",
                "username": "online-user",
                "client_code": "CLIENT-GROUP-ONLINE",
                "status": "online",
                "ws_connected": True,
                "group_name": "BAIRAKTARIS",
                "app_version": "1.0.13",
            },
            {
                "display_name": "GROUPED OFFLINE",
                "pc_name": "OFFLINE-PC",
                "username": "offline-user",
                "client_code": "CLIENT-GROUP-OFFLINE",
                "status": "offline",
                "ws_connected": False,
                "group_name": "BAIRAKTARIS",
                "app_version": "1.0.13",
            },
            {
                "display_name": "UNGROUPED CLIENT",
                "pc_name": "OTHER-PC",
                "username": "other-user",
                "client_code": "CLIENT-OTHER",
                "status": "online",
                "ws_connected": True,
                "group_name": "Ungrouped",
                "app_version": "1.0.13",
            },
        ]
        self.view.update_clients(grouped_clients, force=True)
        self.view.group_option.configure(values=["All Groups", "BAIRAKTARIS"])
        self.view.group_option.set("BAIRAKTARIS")
        self.view._apply_filters()
        self.root.update()

        self.assertEqual(
            set(self.view.client_rows),
            {"CLIENT-GROUP-ONLINE", "CLIENT-GROUP-OFFLINE"},
        )

        online_row = self.view.client_rows["CLIENT-GROUP-ONLINE"]
        self.assertEqual(online_row["status_label"].cget("background"), COLORS.success)
        self.assertEqual(online_row["status_text"].cget("text"), "ONLINE  ·  CONNECTED")
        self.assertEqual(online_row["status_text"].cget("background"), COLORS.success_soft)

        offline_row = self.view.client_rows["CLIENT-GROUP-OFFLINE"]
        self.assertEqual(offline_row["status_label"].cget("background"), COLORS.danger)
        self.assertEqual(offline_row["status_text"].cget("text"), "OFFLINE")
        self.assertEqual(offline_row["status_text"].cget("background"), COLORS.danger_soft)

        for row in (online_row, offline_row):
            self.assertTrue(row["status_label"].winfo_ismapped())
            self.assertTrue(row["status_text"].winfo_ismapped())
            self.assertEqual(row["status_text"].winfo_y(), 0)
            self.assertEqual(row["buttons_frame"].winfo_y(), 38)

    def test_toolbar_stacks_on_compact_window_and_shortcuts_work(self):
        """Η toolbar γίνεται δεύτερη σειρά χωρίς να χάνονται τα actions."""

        self.root.geometry("950x700")
        self.root.update()
        self.view._apply_layout()
        self.assertFalse(self.view._wide_layout)
        self.assertEqual(int(self.view.actions_frame.grid_info()["row"]), 1)
        self.view.set_connection_status("Online")
        self.assertEqual(
            self.view.connection_status_label.cget("text"), "Dashboard online"
        )
        self.root.focus_force()
        self.root.event_generate("<F5>", when="tail")
        self.root.update()
        self.refresh.assert_called_once()

    def test_client_list_uses_pages_of_twenty_five_rows(self):
        """Η μεγάλη λίστα δημιουργεί μόνο τα rows της ενεργής σελίδας."""

        clients = [
            {
                "display_name": f"CLIENT {index:03d}",
                "pc_name": f"PC-{index:03d}",
                "username": "user",
                "client_code": f"CLIENT-{index:03d}",
                "status": "online" if index % 2 == 0 else "offline",
                "ws_connected": index % 2 == 0,
                "group_name": "Ungrouped",
                "app_version": "1.0.13",
            }
            for index in range(60)
        ]

        self.view.update_clients(clients, force=True)
        self.root.update()
        self.assertEqual(len(self.view.client_rows), 25)
        self.assertEqual(self.view.page_label.cget("text"), "Page 1 / 3")
        self.assertEqual(self.view.count_label.cget("text"), "60 / 60 shown")

        self.view._change_page(1)
        self.root.update()
        self.assertEqual(len(self.view.client_rows), 25)
        self.assertEqual(self.view.page_label.cget("text"), "Page 2 / 3")
        self.assertIn("CLIENT-025", self.view.client_rows)

        self.view._change_page(1)
        self.root.update()
        self.assertEqual(len(self.view.client_rows), 10)
        self.assertEqual(self.view.page_label.cget("text"), "Page 3 / 3")
        self.assertIn("CLIENT-050", self.view.client_rows)
        self.assertEqual(self.view.next_page_button.cget("state"), "disabled")

    def test_manage_tabs_remain_visible_after_large_client_list(self):
        """Τα tabs μετά το Provider αποδίδονται ενώ υπάρχει μεγάλη λίστα."""

        from app.views.client_manage_window import ClientManageWindow

        clients = [
            {
                "display_name": f"CLIENT {index:03d}",
                "pc_name": f"PC-{index:03d}",
                "username": "user",
                "client_code": f"CLIENT-{index:03d}",
                "status": "online" if index % 3 else "offline",
                "ws_connected": index % 3 != 0,
                "group_name": "BAIRAKTARIS" if index < 8 else "Ungrouped",
                "app_version": "1.0.13",
            }
            for index in range(248)
        ]
        self.view.update_clients(clients, force=True)
        self.root.update()
        self.assertEqual(len(self.view.client_rows), 25)

        manage = ClientManageWindow(self.root, clients[1])
        manage.geometry("1600x900")
        self.root.update()

        try:
            tabs = (
                ("Provider", manage.provider_tab, manage.provider_tab_view),
                ("Services", manage.services_tab, manage.services_tab_view),
                ("Processes", manage.processes_tab, manage.processes_tab_view),
                ("Updates", manage.updates_tab, manage.updates_tab_view),
                (
                    "Senario Prosorinon",
                    manage.senario_prosorinon_tab,
                    manage.senario_prosorinon_tab_view,
                ),
            )
            for tab_name, tab, tab_view in tabs:
                with self.subTest(tab=tab_name):
                    manage.tabs.set(tab_name)
                    for _ in range(5):
                        self.root.update()
                        time.sleep(0.05)
                    self.assertEqual(manage.tabs.get(), tab_name)
                    self.assertTrue(tab.winfo_ismapped())
                    self.assertTrue(tab_view.winfo_ismapped())
                    self.assertGreater(len(tab_view.winfo_children()), 0)
        finally:
            manage.destroy()
            self.root.update()


if __name__ == "__main__":
    unittest.main()
