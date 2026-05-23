import logging
from fastapi import APIRouter

from app.config import AppConfig


router = APIRouter(prefix="/api", tags=["Health"])
logger = logging.getLogger(__name__)


class HealthRoutes:
    """
    Κλάση που περιέχει τα health endpoints του server.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί τις ρυθμίσεις του server.
        """

        self.config = AppConfig()

    def get_health(self) -> dict:
        """
        Επιστρέφει την κατάσταση λειτουργίας του server.
        """

        logger.info("Health check request received.")

        return {
            "status": "ok",
            "app_name": self.config.app_name,
            "app_version": self.config.app_version,
            "environment": self.config.environment
        }


health_routes = HealthRoutes()


@router.get("/health")
def health_check() -> dict:
    """
    Endpoint ελέγχου λειτουργίας server.
    """

    return health_routes.get_health()