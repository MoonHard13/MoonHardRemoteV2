import certifi
import hashlib
import json
import re
import shutil
import ssl
import stat
import time
import urllib.request
import zipfile

from pathlib import Path

from urllib.error import URLError, HTTPError

from app.config import ClientConfig


class ClientUpdateChecker:
    """
    Ελέγχει την έκδοση του client σε σχέση με το update manifest του server.
    """
    
    PACKAGE_DOWNLOAD_MAX_ATTEMPTS = 5
    PACKAGE_DOWNLOAD_TIMEOUT_SECONDS = 180
    PACKAGE_RETRY_HTTP_CODES = {408, 429, 500, 502, 503, 504}
    
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
            with urllib.request.urlopen(
                request,
                timeout=15,
                context=self._create_ssl_context()
            ) as response:
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

        last_error: Exception | None = None

        for attempt in range(1, self.PACKAGE_DOWNLOAD_MAX_ATTEMPTS + 1):
            try:
                if package_path.exists():
                    package_path.unlink()

                with urllib.request.urlopen(
                    request,
                    timeout=self.PACKAGE_DOWNLOAD_TIMEOUT_SECONDS,
                    context=self._create_ssl_context()
                ) as response:
                    with package_path.open("wb") as output_file:
                        while True:
                            chunk = response.read(1024 * 1024)

                            if not chunk:
                                break

                            output_file.write(chunk)

                last_error = None
                break

            except HTTPError as exc:
                last_error = exc

                if exc.code not in self.PACKAGE_RETRY_HTTP_CODES:
                    raise RuntimeError(f"Package HTTP error: {exc.code}") from exc

                if attempt >= self.PACKAGE_DOWNLOAD_MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Package HTTP error: {exc.code} after {attempt} attempts"
                    ) from exc

                retry_delay = self._calculate_retry_delay_seconds(attempt)
                time.sleep(retry_delay)

            except URLError as exc:
                last_error = exc

                if attempt >= self.PACKAGE_DOWNLOAD_MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Package connection error after {attempt} attempts: {exc.reason}"
                    ) from exc

                retry_delay = self._calculate_retry_delay_seconds(attempt)
                time.sleep(retry_delay)

            except TimeoutError as exc:
                last_error = exc

                if attempt >= self.PACKAGE_DOWNLOAD_MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Package download timeout after {attempt} attempts"
                    ) from exc

                retry_delay = self._calculate_retry_delay_seconds(attempt)
                time.sleep(retry_delay)

        if last_error is not None:
            raise RuntimeError(f"Package download failed: {last_error}")

        if not package_path.exists():
            raise FileNotFoundError(f"Package was not downloaded: {package_path}")

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
        Περιλαμβάνει Zip Slip protection ώστε κανένα αρχείο να μη βγει εκτός extracted_dir.
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
                self._safe_extract_zip(
                    zip_file=zip_file,
                    destination_dir=extracted_dir
                )

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

    def _safe_extract_zip(
        self,
        zip_file: zipfile.ZipFile,
        destination_dir: Path
    ) -> None:
        """
        Κάνει ασφαλές extract ZIP αρχείου.

        Προστατεύει από:
        - paths με ..
        - absolute paths
        - Windows drive paths όπως C:/...
        - symlinks μέσα στο ZIP
        - αρχεία που προσπαθούν να γραφτούν εκτός destination_dir
        """

        destination_dir_resolved = destination_dir.resolve()

        for member in zip_file.infolist():
            safe_member_name = self._validate_zip_member_path(
                member=member,
                destination_dir=destination_dir_resolved
            )

            target_path = (destination_dir_resolved / safe_member_name).resolve()

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)

            with zip_file.open(member, "r") as source_file:
                with target_path.open("wb") as target_file:
                    shutil.copyfileobj(source_file, target_file)

    def _validate_zip_member_path(
        self,
        member: zipfile.ZipInfo,
        destination_dir: Path
    ) -> Path:
        """
        Ελέγχει ότι ένα ZIP member είναι ασφαλές για extract.
        Επιστρέφει normalized relative path.
        """

        member_name = str(member.filename or "").replace("\\", "/").strip()

        if not member_name:
            raise RuntimeError("ZIP contains an empty member name.")

        if "\x00" in member_name:
            raise RuntimeError(f"ZIP contains invalid null byte path: {member.filename}")

        if member_name.startswith("/"):
            raise RuntimeError(f"ZIP contains absolute path: {member.filename}")

        if re.match(r"^[A-Za-z]:", member_name):
            raise RuntimeError(f"ZIP contains Windows drive path: {member.filename}")

        member_path = Path(member_name)

        if any(part in ("..", "") for part in member_path.parts):
            raise RuntimeError(f"ZIP contains unsafe relative path: {member.filename}")

        member_mode = member.external_attr >> 16

        if stat.S_ISLNK(member_mode):
            raise RuntimeError(f"ZIP contains symlink, which is not allowed: {member.filename}")

        target_path = (destination_dir / member_path).resolve()

        try:
            target_path.relative_to(destination_dir)
        except ValueError as exc:
            raise RuntimeError(f"ZIP member escapes destination folder: {member.filename}") from exc

        return member_path

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

    def _calculate_retry_delay_seconds(self, attempt: int) -> int:
        """
        Υπολογίζει καθυστέρηση retry για προσωρινά download errors.
        """

        retry_delays = {
            1: 5,
            2: 10,
            3: 20,
            4: 40
        }

        return retry_delays.get(attempt, 60)

    def _calculate_sha256(self, file_path: Path) -> str:
        """
        Υπολογίζει το SHA256 ενός αρχείου.
        """

        sha256_hash = hashlib.sha256()

        with file_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        Δημιουργεί SSL context με αξιόπιστα certificates από το certifi.
        """

        return ssl.create_default_context(cafile=certifi.where())