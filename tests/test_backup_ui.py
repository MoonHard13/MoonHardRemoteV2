"""Δοκιμές της responsive διεπαφής του Backup Manager."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))


@unittest.skipUnless(
    importlib.util.find_spec("customtkinter")
    and (os.name == "nt" or os.environ.get("DISPLAY")),
    "Απαιτεί οθόνη και CustomTkinter.",
)
class BackupManagerUITests(unittest.TestCase):
    """Ελέγχει πραγματικά widgets χωρίς σύνδεση σε Client ή SQL Server."""

    def setUp(self):
        import customtkinter as ctk
        from app.views.manage.backup_window import BackupManagerWindow

        self.root = ctk.CTk()
        self.root.withdraw()
        self.requests = Mock(return_value=True)
        self.window = BackupManagerWindow(
            self.root,
            client_code="CLIENT-TEST",
            get_bo_values_callback=lambda: [
                "ID 1 - InitialTest",
                "ID 3 - IthakiTest",
            ],
            get_selected_bo_id_callback=lambda: 1,
            on_request_callback=self.requests,
        )
        for job in self.window._lifecycle_jobs:
            try:
                self.window.after_cancel(job)
            except Exception:
                pass
        self.window._lifecycle_jobs.clear()
        self.window.geometry("1220x820")
        self.window.update()
        self.window._apply_layout()
        self.window.update()

    def tearDown(self):
        if not self.window._destroying:
            self.window.destroy()
        for job in self.root.tk.call("after", "info"):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.root.destroy()

    def test_wide_workspace_keeps_settings_and_activity_side_by_side(self):
        """Σε μεγάλο παράθυρο το live Activity παραμένει ορατό."""

        self.assertTrue(self.window._wide_layout)
        self.assertEqual(int(self.window.manual_card.grid_info()["row"]), 0)
        self.assertEqual(int(self.window.activity_card.grid_info()["row"]), 0)
        self.assertEqual(int(self.window.activity_card.grid_info()["column"]), 1)
        self.assertGreater(self.window.activity_box.winfo_height(), 280)

    def test_small_workspace_stacks_cards_without_horizontal_clipping(self):
        """Στο ελάχιστο πλάτος τα panels γίνονται μονή στήλη."""

        self.window.geometry("940x700")
        self.window.update()
        self.window._apply_layout()
        self.assertFalse(self.window._wide_layout)
        self.assertEqual(int(self.window.activity_card.grid_info()["column"]), 0)
        self.assertEqual(int(self.window.activity_card.grid_info()["row"]), 1)

        self.window.tabs.set("Schedules")
        self.window.update_idletasks()
        self.assertEqual(
            int(self.window.schedule_destination_card.grid_info()["row"]), 2
        )

    def test_destination_form_switches_local_and_cloud_fields(self):
        """Το compact form δείχνει μόνο τα σχετικά πεδία προορισμού."""

        form = self.window.manual_form
        self.assertTrue(form._field_frames[form.destination_path].winfo_ismapped())
        self.assertFalse(form._field_frames[form.cloud_remote].winfo_ismapped())

        form.destination_type.set("Cloud via rclone")
        form._refresh_states()
        form.cloud_remote.insert(0, "mega:MoonHard/SQL")
        self.window.update_idletasks()
        settings = form.get_settings()
        self.assertEqual(settings["destination_type"], "cloud")
        self.assertEqual(settings["cloud_remote"], "mega:MoonHard/SQL")
        self.assertFalse(form._field_frames[form.destination_path].winfo_ismapped())
        self.assertTrue(form._field_frames[form.staging_path].winfo_ismapped())

    def test_schedule_editor_preserves_strict_protocol_payload(self):
        """Ο νέος editor δεν αλλάζει το υπάρχον schedule contract."""

        self.window.tabs.set("Schedules")
        self.window.schedule_name.insert(0, "Nightly InitialTest")
        self.window.frequency_option.set("Weekly")
        self.window.weekday_option.set("Wednesday")
        self.window._refresh_schedule_states()
        payload = self.window._schedule_payload()
        self.assertEqual(
            set(payload),
            {
                "schedule_id",
                "name",
                "bo_connection_id",
                "frequency",
                "time",
                "weekday",
                "day_of_month",
                "enabled",
                "settings",
            },
        )
        self.assertEqual(payload["frequency"], "weekly")
        self.assertEqual(payload["weekday"], 2)
        self.assertEqual(payload["bo_connection_id"], 1)

    def test_manual_request_copy_clear_and_status_pill(self):
        """Primary action, clipboard και status παραμένουν λειτουργικά."""

        from app.ui.theme import COLORS

        with patch(
            "app.views.manage.backup_window.messagebox.askyesno",
            return_value=True,
        ):
            self.window.run_manual_backup()
        request = self.requests.call_args.args[0]
        self.assertEqual(request["type"], "backup_request")
        self.assertEqual(request["operation"], "run")
        self.assertEqual(request["bo_connection_id"], 1)

        self.window._set_activity("backup detail")
        self.window.copy_activity()
        self.assertEqual(self.window.clipboard_get(), "backup detail")
        self.assertEqual(self.window.status_label.cget("fg_color"), COLORS.success_soft)
        self.window.clear_activity()
        self.assertIn("Ready", self.window.activity_box.get("1.0", "end-1c"))
        self.assertEqual(self.window.progress_bar.get(), 0)


if __name__ == "__main__":
    unittest.main()
