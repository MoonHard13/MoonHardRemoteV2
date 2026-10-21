"""Contract tests για σταθερό Windows client build toolchain."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ClientBuildDependencyTests(unittest.TestCase):
    """Ελέγχει το dependency που παρέχει το legacy pkg_resources API."""

    def test_setuptools_is_pinned_to_pkg_resources_compatible_version(self):
        requirements = (
            ROOT / "updater" / "requirements.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("setuptools==80.9.0", requirements)

    def test_client_build_scripts_verify_pkg_resources(self):
        for relative_path in (
            "scripts/build_client_update_package.ps1",
            "scripts/build_client_installer.ps1",
        ):
            source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
            self.assertIn('python -c "import pkg_resources"', source)
            self.assertIn("Build dependency check failed: pkg_resources is unavailable", source)


if __name__ == "__main__":
    unittest.main()
