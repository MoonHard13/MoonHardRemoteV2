import json
import urllib.request
import hashlib
import shutil
import zipfile

from pathlib import Path

from urllib.error import URLError, HTTPError

from app.config import ClientConfig


class ClientUpdateChecker:
    """
    Ελέγχει την έκδοση του client σε σχέση με το update manifest του server.
    """

    def __init__(self, config: ClientConfig) -> None:
        """
        Αρχικοποιεί τον update checker.
        """

        self.config = config

    def check_for_update(self) -> dict:
        """
        Ελέγχει αν υπάρχει νεότερη έκδοση client.
        """

        current_version = self.config.app_version
        manifest_url = self._build_manifest_url()

        try:
            manifest = self._download_manifest(manifest_url)
            latest_version = str(manifest.get("latest_version", "")).strip()

            update_available = self._is_version_newer(
                latest_version=latest_version,
                current_version=current_version
            )

            return {
                "success": True,
                "current_version": current_version,
                "latest_version": latest_version,
                "update_available": update_available,
                "download_url": manifest.get("download_url", ""),
                "sha256": manifest.get("sha256", ""),
                "mandatory": bool(manifest.get("mandatory", False)),
                "release_notes": manifest.get("release_notes", ""),
                "manifest_url": manifest_url
            }

        except Exception as exc:
            return {
                "success": False,
                "current_version": current_version,
                "latest_version": "",
                "update_available": False,
                "download_url": "",
                "sha256": "",
                "mandatory": False,
                "release_notes": "",
                "manifest_url": manifest_url,
                "error": str(exc)
            }

    def _build_manifest_url(self) -> str:
        """
        Δημιουργεί το URL του update manifest από το WebSocket URL.
        """

        websocket_url = self.config.server_websocket_url

        if websocket_url.startswith("wss://"):
            base_url = websocket_url.replace("wss://", "https://", 1)
        elif websocket_url.startswith("ws://"):
            base_url = websocket_url.replace("ws://", "http://", 1)
        else:
            base_url = websocket_url

        if "/ws/client" in base_url:
            base_url = base_url.split("/ws/client", 1)[0]

        return f"{base_url.rstrip('/')}/updates/client/latest"

    def _download_manifest(self, manifest_url: str) -> dict:
        """
        Κατεβάζει το manifest JSON από τον server.
        """

        request = urllib.request.Request(
            manifest_url,
            headers={
                "User-Agent": "MoonHardRemoteV2-ClientUpdater"
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw_data = response.read().decode("utf-8")

        except HTTPError as exc:
            raise RuntimeError(f"Manifest HTTP error: {exc.code}") from exc

        except URLError as exc:
            raise RuntimeError(f"Manifest connection error: {exc.reason}") from exc

        return json.loads(raw_data)

    def _is_version_newer(self, latest_version: str, current_version: str) -> bool:
        """
        Ελέγχει αν η latest έκδοση είναι μεγαλύτερη από την current.
        """

        latest_parts = self._parse_version(latest_version)
        current_parts = self._parse_version(current_version)

        return latest_parts > current_parts

    def _parse_version(self, version: str) -> tuple[int, int, int]:
        """
        Μετατρέπει έκδοση τύπου 1.2.3 σε tuple για ασφαλή σύγκριση.
        """

        parts = str(version or "0.0.0").split(".")
        numbers: list[int] = []

        for part in parts[:3]:
            try:
                numbers.append(int(part))
            except ValueError:
                numbers.append(0)

        while len(numbers) < 3:
            numbers.append(0)

        return tuple(numbers)
    
    def download_update_package(
        self,
        download_url: str,
        expected_sha256: str,
        latest_version: str
    ) -> dict:
        """
        Κατεβάζει το update ZIP από GitHub Releases και κάνει SHA256 verification.
        """

        if not download_url:
            raise ValueError("Download URL is empty.")

        if not expected_sha256:
            raise ValueError("Expected SHA256 is empty.")

        safe_version = str(latest_version or "unknown").strip() or "unknown"

        downloads_dir = (
            Path("C:/ProgramData/MoonHardRemoteV2")
            / "updates"
            / "downloads"
        )
        downloads_dir.mkdir(parents=True, exist_ok=True)

        package_path = downloads_dir / f"moonhard-client-{safe_version}.zip"

        request = urllib.request.Request(
            download_url,
            headers={
                "User-Agent": "MoonHardRemoteV2-ClientUpdater"
            }
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                with package_path.open("wb") as output_file:
                    while True:
                        chunk = response.read(1024 * 1024)

                        if not chunk:
                            break

                        output_file.write(chunk)

        except HTTPError as exc:
            raise RuntimeError(f"Package HTTP error: {exc.code}") from exc

        except URLError as exc:
            raise RuntimeError(f"Package connection error: {exc.reason}") from exc

        actual_sha256 = self._calculate_sha256(package_path)
        sha256_verified = actual_sha256.lower() == expected_sha256.lower()

        if not sha256_verified:
            raise RuntimeError(
                f"SHA256 verification failed. Expected {expected_sha256}, got {actual_sha256}"
            )

        return {
            "success": True,
            "download_url": download_url,
            "saved_path": str(package_path),
            "file_size_bytes": package_path.stat().st_size,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
            "sha256_verified": True,
            "latest_version": latest_version
        }

    def extract_update_package(
        self,
        package_path: str,
        latest_version: str
    ) -> dict:
        """
        Κάνει extract το update ZIP και ελέγχει ότι περιέχει τα βασικά αρχεία client.
        """

        if not package_path:
            raise ValueError("Package path is empty.")

        package_file = Path(package_path)

        if not package_file.exists() or not package_file.is_file():
            raise FileNotFoundError(f"Package file not found: {package_file}")

        safe_version = str(latest_version or "unknown").strip() or "unknown"

        extracted_dir = (
            Path("C:/ProgramData/MoonHardRemoteV2")
            / "updates"
            / "extracted"
            / safe_version
        )

        if extracted_dir.exists():
            shutil.rmtree(extracted_dir)

        extracted_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(package_file, "r") as zip_file:
                zip_file.extractall(extracted_dir)

        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"Invalid ZIP package: {package_file}") from exc

        validation_result = self._validate_extracted_package(extracted_dir)

        if not validation_result["valid"]:
            raise RuntimeError(
                "Extracted package validation failed: "
                + ", ".join(validation_result["missing_items"])
            )

        extracted_files_count = sum(
            1 for item in extracted_dir.rglob("*") if item.is_file()
        )

        return {
            "success": True,
            "package_path": str(package_file),
            "extracted_path": str(extracted_dir),
            "latest_version": latest_version,
            "extracted_files_count": extracted_files_count,
            "required_items": validation_result["required_items"],
            "missing_items": [],
            "package_valid": True
        }

    def _validate_extracted_package(self, extracted_dir: Path) -> dict:
        """
        Ελέγχει ότι το extracted update package έχει την αναμενόμενη δομή.
        """

        required_items = [
            "MoonHardRemoteClient.exe",
            "_internal"
        ]

        missing_items: list[str] = []

        for required_item in required_items:
            required_path = extracted_dir / required_item

            if not required_path.exists():
                missing_items.append(required_item)

        return {
            "valid": len(missing_items) == 0,
            "required_items": required_items,
            "missing_items": missing_items
        }

    def _calculate_sha256(self, file_path: Path) -> str:
        """
        Υπολογίζει το SHA256 ενός αρχείου.
        """

        sha256_hash = hashlib.sha256()

        with file_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()