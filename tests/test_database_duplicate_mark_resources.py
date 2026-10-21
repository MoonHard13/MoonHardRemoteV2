from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "client" / "app" / "sql"


class DuplicateMarkResourceTests(unittest.TestCase):
    def test_success_script_is_present(self):
        path = SQL_DIR / "!Delete_Duplicate_Success_Mark.sql"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("#Conflicts", text)
        self.assertIn("MyDATA_ResponseCancellationMARK", text)

    def test_main_script_is_present_and_has_two_batches(self):
        path = SQL_DIR / "!Delete_Duplicate_MArK.sql"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("DuplicateMArK", text)
        self.assertGreaterEqual(text.lower().count("\ngo\n"), 2)

    def test_standard_update_package_builder_includes_sql_resources(self):
        path = ROOT / "scripts" / "build_client_update_package.ps1"
        text = path.read_text(encoding="utf-8-sig")

        self.assertIn('--add-data ".\\client\\app\\sql;app\\sql"', text)
        self.assertIn('!Delete_Duplicate_Success_Mark.sql', text)
        self.assertIn('!Delete_Duplicate_MArK.sql', text)
        self.assertIn('ValidationSqlResourceDir', text)
        self.assertIn('Missing required SQL resource', text)

    def test_update_package_uses_retrying_tar_zip_creation(self):
        path = ROOT / "scripts" / "build_client_update_package.ps1"
        text = path.read_text(encoding="utf-8-sig")

        self.assertIn("tar.exe -a -c -f $PackageZip *", text)
        self.assertIn("$ZipAttempts = 5", text)
        self.assertIn("Start-Sleep -Seconds 3", text)
        self.assertNotIn("Compress-Archive", text)

    def test_client_release_version_is_1_0_18(self):
        config_text = (ROOT / "client" / "app" / "config.py").read_text(
            encoding="utf-8"
        )
        installer_text = (
            ROOT / "installer" / "MoonHardRemoteClientSetup.iss"
        ).read_text(encoding="utf-8-sig")

        self.assertIn('self.app_version = "1.0.18"', config_text)
        self.assertIn("AppVersion=1.0.18", installer_text)


if __name__ == "__main__":
    unittest.main()
