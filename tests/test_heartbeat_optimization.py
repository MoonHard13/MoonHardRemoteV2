"""Δοκιμές για τη μείωση Supabase heartbeat writes και log ingestion."""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HeartbeatOptimizationTests(unittest.TestCase):
    """Ελέγχει το συμβόλαιο του optimized heartbeat flow."""

    def test_client_heartbeat_interval_is_sixty_seconds(self):
        """Ο client δεν πρέπει να στέλνει application heartbeat κάθε 25 δευτερόλεπτα."""

        source = (PROJECT_ROOT / "client/app/config.py").read_text(encoding="utf-8")

        self.assertIn("self.heartbeat_seconds = 60", source)
        self.assertNotIn("self.heartbeat_seconds = 25", source)

    def test_server_persists_heartbeat_at_most_hourly(self):
        """Το heartbeat checkpoint στη Supabase πρέπει να γίνεται ανά 60 λεπτά."""

        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self.heartbeat_db_write_interval_seconds = 3600", source)
        self.assertNotIn("self.heartbeat_db_write_interval_seconds = 300", source)

    def test_server_keeps_live_last_seen_in_memory(self):
        """Το live last_seen πρέπει να ενημερώνεται στη RAM για connected clients."""

        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("self.client_memory_last_seen: dict[str, datetime] = {}", source)
        self.assertIn("def _record_memory_heartbeat", source)
        self.assertIn('client["last_seen"] = memory_last_seen.isoformat()', source)

    def test_first_heartbeat_does_not_force_second_database_write(self):
        """Το register πρέπει να ξεκινά τον checkpoint timer πριν από το πρώτο heartbeat."""

        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "self.client_last_db_heartbeat[client_code] = registered_at",
            source,
        )

    def test_heartbeat_is_not_logged_at_info_level(self):
        """Τα συχνά heartbeat messages δεν πρέπει να γεμίζουν τα INFO logs."""

        source = (
            PROJECT_ROOT / "server/app/routes/websocket_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'elif message_type == "heartbeat":\n'
            '                    logger.debug("Client heartbeat received from %s", client_code)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
