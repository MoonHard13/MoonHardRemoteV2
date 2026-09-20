"""Δοκιμές για το navigation bar του Manage window."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))


class ManageTabNavigationSourceTests(unittest.TestCase):
    """Ελέγχει το tab styling χωρίς γραφικό περιβάλλον."""

    def test_manage_tabs_use_full_navigation_styling(self):
        """Το default segmented control έχει αντικατασταθεί οπτικά."""

        source = (
            PROJECT_ROOT / "dashboard/app/views/client_manage_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.tabs = ManageTabView(self)", source)
        self.assertNotIn("CTkTabview", source)

        navigation_source = (
            PROJECT_ROOT / "dashboard/app/views/manage/tab_navigation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class ManageTabView(ctk.CTkFrame)", navigation_source)
        self.assertIn("font=FONTS.body_bold", navigation_source)
        self.assertIn("fg_color=COLORS.accent", navigation_source)
        self.assertIn("hover_color=COLORS.surface_hover", navigation_source)
        self.assertIn("def _layout_navigation", navigation_source)
        self.assertNotIn("_segmented_button", navigation_source)
        self.assertNotIn("_buttons_dict", navigation_source)

    def test_dashboard_uses_customtkinter_6(self):
        """Το Dashboard παραμένει κλειδωμένο στη νέα major έκδοση."""

        requirements = (
            PROJECT_ROOT / "dashboard/requirements.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("customtkinter==6.0.0", requirements)

    def test_manage_tabs_have_keyboard_shortcuts(self):
        """Κάθε tab διαθέτει shortcut από Alt+1 έως Alt+0."""

        source = (
            PROJECT_ROOT / "dashboard/app/views/client_manage_window.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _bind_tab_shortcuts", source)
        self.assertIn('shortcut_keys = tuple(str(index)', source)
        self.assertIn('self.bind(', source)
        self.assertIn('f"<Alt-Key-{key}>"', source)


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class ManageTabNavigationUITests(unittest.TestCase):
    """Ελέγχει τα πραγματικά navigation widgets."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.client_manage_window import ClientManageWindow

        self.root = ctk.CTk()
        self.root.geometry("1600x900")
        self.window = ClientManageWindow(
            self.root,
            {
                "client_code": "CLIENT-TEST",
                "display_name": "TEST CLIENT",
                "pc_name": "TEST-PC",
                "username": "user",
                "status": "online",
                "ws_connected": True
            }
        )
        self.window.geometry("1600x900")
        self.root.update()

    def tearDown(self):
        if self.window.winfo_exists():
            self.window.destroy()
        self.root.destroy()

    def test_navigation_styling_and_tab_switching_are_available(self):
        """Το navigation χρησιμοποιεί public styling και αλλάζει tabs."""

        from app.ui.theme import COLORS

        self.assertEqual(
            self.window.tabs.button("Overview").cget("fg_color"),
            COLORS.accent
        )

        result = self.window._select_tab("Provider")
        self.root.update()
        self.assertEqual(result, "break")
        self.assertEqual(self.window.tabs.get(), "Provider")
        self.assertEqual(
            self.window.tabs.button("Provider").cget("fg_color"),
            COLORS.accent
        )
        self.assertEqual(
            self.window.tabs.button("Overview").cget("fg_color"),
            "transparent"
        )
        self.assertTrue(self.window.provider_tab_view.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
