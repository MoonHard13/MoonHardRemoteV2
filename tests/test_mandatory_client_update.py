"""Contract tests για automatic mandatory client updates."""

import ast
import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MandatoryClientUpdateTests(unittest.TestCase):
    """Ελέγχει ότι το mandatory manifest μπορεί να ξεκινήσει ασφαλές auto update."""

    def test_server_route_is_valid_python(self):
        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")
        ast.parse(source)

    def test_dashboard_files_are_valid_python(self):
        for relative_path in (
            "dashboard/app/dashboard_app.py",
            "dashboard/app/views/client_manage_window.py",
            "dashboard/app/views/manage/updates_tab.py",
        ):
            source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            ast.parse(source)

    def test_server_reads_manifest_and_tracks_mandatory_state(self):
        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "from app.routes.update_routes import manifest_service",
            source,
        )
        self.assertIn("self.mandatory_update_states: dict[str, dict] = {}", source)
        self.assertIn("def _start_mandatory_update_if_needed", source)
        self.assertIn("def _handle_mandatory_update_result", source)

    def test_mandatory_update_starts_immediately_after_register(self):
        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        register_send = source.index('"type": "registered"')
        mandatory_start = source.index(
            "await self._start_mandatory_update_if_needed(",
            register_send,
        )

        self.assertGreater(mandatory_start, register_send)

    def test_mandatory_flow_uses_existing_client_update_protocol(self):
        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"type": "client_update_download"', source)
        self.assertIn('"type": "client_update_extract"', source)
        self.assertIn('"type": "client_update_apply"', source)
        self.assertIn("sha256_verified", source)
        self.assertIn("package_valid", source)

    def test_failed_update_keeps_client_and_uses_retry_cooldown(self):
        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self.mandatory_update_retry_cooldown_seconds = 900", source)
        self.assertIn("def _fail_mandatory_update", source)
        self.assertIn("The current client remains active.", source)

    def test_dashboard_displays_mandatory_update_status(self):
        dashboard_source = (
            PROJECT_ROOT / "dashboard/app/dashboard_app.py"
        ).read_text(encoding="utf-8")
        manage_source = (
            PROJECT_ROOT / "dashboard/app/views/client_manage_window.py"
        ).read_text(encoding="utf-8")
        updates_source = (
            PROJECT_ROOT / "dashboard/app/views/manage/updates_tab.py"
        ).read_text(encoding="utf-8")

        self.assertIn('message_type == "mandatory_client_update_status"', dashboard_source)
        self.assertIn("handle_mandatory_client_update_status", manage_source)
        self.assertIn("handle_mandatory_update_status", updates_source)

    def test_dashboard_version_is_1_0_4(self):
        source = (
            PROJECT_ROOT / "dashboard/app/config.py"
        ).read_text(encoding="utf-8")

        self.assertIn('self.app_version = "1.0.4"', source)

    def test_current_manifest_does_not_force_existing_1_0_16_clients(self):
        manifest = json.loads(
            (PROJECT_ROOT / "server/app/update_manifest.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["latest_version"], "1.0.16")
        self.assertFalse(manifest["mandatory"])


if __name__ == "__main__":
    unittest.main()
