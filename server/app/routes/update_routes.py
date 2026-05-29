import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/updates", tags=["updates"])


class UpdateManifestService:
    """
    Διαβάζει το update manifest για τον MoonHard Remote Client.
    """

    def __init__(self) -> None:
        """
        Ορίζει τη διαδρομή του manifest αρχείου.
        """

        self.manifest_path = Path(__file__).resolve().parent.parent / "update_manifest.json"

    def get_client_manifest(self) -> dict:
        """
        Επιστρέφει το manifest του client update.
        """

        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Update manifest was not found: {self.manifest_path}"
            )

        with self.manifest_path.open("r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)

        required_fields = {
            "product",
            "latest_version",
            "download_url",
            "sha256",
            "mandatory",
            "release_notes"
        }

        missing_fields = required_fields - set(manifest.keys())

        if missing_fields:
            raise ValueError(
                f"Update manifest is missing fields: {', '.join(sorted(missing_fields))}"
            )

        return manifest


manifest_service = UpdateManifestService()


@router.get("/client/latest")
async def get_latest_client_update() -> dict:
    """
    Επιστρέφει την τελευταία διαθέσιμη έκδοση του MoonHard Remote Client.
    """

    try:
        return manifest_service.get_client_manifest()

    except FileNotFoundError as exc:
        logger.exception("Client update manifest file was not found.")
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("Failed to read client update manifest.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc