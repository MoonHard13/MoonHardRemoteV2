import json
import urllib.request
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