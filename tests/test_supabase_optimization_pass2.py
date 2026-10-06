"""Στατικές δοκιμές για το Supabase optimization pass 2."""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SupabaseOptimizationPass2Tests(unittest.TestCase):
    """Ελέγχει ότι τα βασικά contracts μείωσης Supabase API calls παραμένουν ενεργά."""

    def test_registration_reuses_security_read(self):
        """Το register πρέπει να επαναχρησιμοποιεί το security record αντί για δεύτερο clients GET."""

        repository_source = (
            PROJECT_ROOT / "server/app/repositories/client_repository.py"
        ).read_text(encoding="utf-8")

        websocket_source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("existing_client_checked: bool = False", repository_source)
        self.assertIn("existing_client_record=security_record", websocket_source)
        self.assertIn("existing_client_checked=True", websocket_source)

    def test_token_last_seen_is_merged_into_connect_update(self):
        """Το token audit timestamp δεν πρέπει να απαιτεί ξεχωριστό PATCH σε κάθε reconnect."""

        repository_source = (
            PROJECT_ROOT / "server/app/repositories/client_repository.py"
        ).read_text(encoding="utf-8")

        websocket_source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("def should_touch_client_token_last_seen", repository_source)
        self.assertIn('update_payload["client_token_last_seen_at"] = now_utc', repository_source)
        self.assertNotIn(
            "self.client_repository.touch_client_token_last_seen(client_code)",
            websocket_source,
        )

    def test_appsettings_cache_skips_unchanged_reconnect_writes(self):
        """Τα ίδια AppSettings πρέπει να συγκρίνονται από cache πριν γίνει Supabase upsert."""

        source = (
            PROJECT_ROOT / "server/app/repositories/client_repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn("def _ensure_appsettings_cache_loaded", source)
        self.assertIn("self._appsettings_cache_loaded = True", source)
        self.assertIn("if cached_hash == payload_hash:", source)
        self.assertIn('"last_read_at"', source)
        self.assertIn("comparable_keys = (", source)

    def test_targeted_dashboard_updates_reuse_existing_payload(self):
        """Connect/disconnect updates δεν πρέπει να απαιτούν νέο view GET όταν έχουμε ήδη row."""

        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self.client_dashboard_cache: dict[str, dict] = {}", source)
        self.assertIn("client=saved_client", source)
        self.assertIn("client=offline_client", source)
        self.assertIn("client=renamed_client", source)

    def test_dashboard_full_refresh_is_thirty_minutes(self):
        """Το safety reconciliation του Dashboard πρέπει να γίνεται ανά 30 λεπτά."""

        source = (
            PROJECT_ROOT / "dashboard/app/dashboard_app.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self.clients_auto_refresh_interval_ms: int = 1800000", source)
        self.assertIn("κάθε 30 λεπτά", source)
        self.assertNotIn("self.clients_auto_refresh_interval_ms: int = 600000", source)

    def test_dashboard_version_bumped(self):
        """Η αλλαγή Dashboard πρέπει να έχει νέα έκδοση για ασφαλές distribution."""

        source = (
            PROJECT_ROOT / "dashboard/app/config.py"
        ).read_text(encoding="utf-8")

        self.assertIn('self.app_version = "1.0.4"', source)


if __name__ == "__main__":
    unittest.main()
