from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = ROOT / "dashboard"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from app.views.manage.provider_ergonomic_tab import ErgonomicProviderTab  # noqa: E402


class ProviderUiErgonomicsTests(unittest.TestCase):
    def test_layout_overrides_are_present(self) -> None:
        for method_name in ("_build_ui", "_build_actions", "_apply_layout"):
            self.assertIn(method_name, ErgonomicProviderTab.__dict__)

    def test_actions_have_stable_single_row_order(self) -> None:
        self.assertEqual(
            ErgonomicProviderTab.ACTION_ORDER,
            (
                "send_selected",
                "send_all",
                "errors",
                "payways",
                "delete_mydata",
            ),
        )

    def test_action_layout_never_uses_compact_second_row(self) -> None:
        source = inspect.getsource(ErgonomicProviderTab._apply_layout)
        self.assertNotIn("compact_positions", source)
        self.assertIn("row=0", source)
        self.assertIn("provider_action_buttons", source)

    def test_actions_are_integrated_into_results_card(self) -> None:
        source = inspect.getsource(ErgonomicProviderTab._build_actions)
        self.assertIn("self.provider_actions_card = self.provider_table_card", source)
        self.assertIn("self.provider_table_card", source)

    def test_results_table_requests_more_visible_rows(self) -> None:
        source = inspect.getsource(ErgonomicProviderTab._build_ui)
        self.assertIn("height=22", source)
        self.assertIn("grid_rowconfigure(2, weight=1)", source)


if __name__ == "__main__":
    unittest.main()
