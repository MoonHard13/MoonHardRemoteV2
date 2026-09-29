from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_FILE = ROOT / "server" / "app" / "websocket" / "database_movement_transfer_extension.py"
CLIENT_FILE = ROOT / "client" / "app" / "registry_client_extension.py"


class MovementTransferRouterContractTests(unittest.TestCase):
    def test_actions_and_parameter_allowlists_exist(self):
        source = ROUTER_FILE.read_text(encoding="utf-8")
        for action in (
            "movement_stations",
            "movement_receipt_search",
            "movement_transfer_date",
            "movement_transfer_receipt",
        ):
            self.assertIn(action, source)
        self.assertIn("old_date", source)
        self.assertIn("real_date", source)
        self.assertIn("new_date", source)
        self.assertIn("station_oid", source)
        self.assertIn("pos_hdr", source)

    def test_capability_gates_old_clients(self):
        router_source = ROUTER_FILE.read_text(encoding="utf-8")
        client_source = CLIENT_FILE.read_text(encoding="utf-8")
        self.assertIn("database_movement_transfer_v1", router_source)
        self.assertIn("database_movement_transfer_v1", client_source)
        self.assertIn("client_supports", router_source)

    def test_transfer_progress_is_forwarded(self):
        source = ROUTER_FILE.read_text(encoding="utf-8")
        self.assertIn("PROGRESS_ACTIONS", source)
        self.assertIn("percent", source)
        self.assertIn("stage", source)
        self.assertIn("message", source)


if __name__ == "__main__":
    unittest.main()
