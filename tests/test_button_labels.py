"""UI contract tests για καθαρά button labels χωρίς shortcut hints."""

import ast
from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"


class ButtonLabelTests(unittest.TestCase):
    """Τα shortcuts παραμένουν ενεργά, αλλά δεν εμφανίζονται πάνω στα κουμπιά."""

    SHORTCUT_PATTERN = re.compile(
        r"(?:Ctrl|Alt|Shift)\+|\bF\d{1,2}\b|\bEsc\b",
        re.IGNORECASE,
    )

    def test_dashboard_button_labels_do_not_show_shortcuts(self):
        offenders: list[str] = []

        for path in DASHBOARD_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                func = node.func
                is_button = (
                    isinstance(func, ast.Attribute)
                    and func.attr == "CTkButton"
                )

                if not is_button:
                    continue

                text_value = None

                for keyword in node.keywords:
                    if keyword.arg != "text":
                        continue

                    if isinstance(keyword.value, ast.Constant) and isinstance(
                        keyword.value.value,
                        str,
                    ):
                        text_value = keyword.value.value
                    break

                if text_value and self.SHORTCUT_PATTERN.search(text_value):
                    relative = path.relative_to(PROJECT_ROOT)
                    offenders.append(f"{relative}: {text_value}")

        self.assertEqual(
            offenders,
            [],
            "Button labels must show only the action name; shortcuts stay bound but hidden. "
            + " | ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
