import logging

from fastapi import APIRouter, Header, HTTPException

from app.config import AppConfig
from app.repositories.client_repository import ClientRepository


router = APIRouter(prefix="/api/clients", tags=["Clients"])
logger = logging.getLogger(__name__)

config = AppConfig()


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")
) -> None:
    """
    Ελέγχει το admin token για REST endpoints.
    Τα WebSocket tokens παραμένουν ξεχωριστά.
    """

    expected_token = config.admin_token

    if not expected_token:
        logger.error("ADMIN_TOKEN is not configured.")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN is not configured."
        )

    if not x_admin_token or x_admin_token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token."
        )


class ClientRoutes:
    """
    Routes για έλεγχο και εμφάνιση clients.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί το repository των clients.
        """

        self.client_repository = ClientRepository()

    def get_clients(self) -> dict:
        """
        Επιστρέφει όλους τους clients από τη βάση.
        """

        try:
            clients = self.client_repository.get_all_clients()

            return {
                "success": True,
                "count": len(clients),
                "clients": clients
            }

        except Exception as exc:
            logger.exception("Failed to fetch clients.")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def create_test_client(self) -> dict:
        """
        Δημιουργεί ή ενημερώνει έναν test client.
        Επιτρέπεται μόνο εκτός production.
        """

        if config.environment.lower() == "production":
            raise HTTPException(
                status_code=403,
                detail="Test client endpoint is disabled in production."
            )

        try:
            client = self.client_repository.upsert_test_client()

            return {
                "success": True,
                "message": "Test client saved successfully.",
                "client": client
            }

        except Exception as exc:
            logger.exception("Failed to create test client.")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def delete_test_client(self) -> dict:
        """
        Διαγράφει τον test client.
        Επιτρέπεται μόνο εκτός production.
        """

        if config.environment.lower() == "production":
            raise HTTPException(
                status_code=403,
                detail="Test client endpoint is disabled in production."
            )

        try:
            result = self.client_repository.delete_test_client()

            return {
                "success": True,
                "message": "Test client deleted successfully.",
                "result": result
            }

        except Exception as exc:
            logger.exception("Failed to delete test client.")
            raise HTTPException(status_code=500, detail=str(exc)) from exc


client_routes = ClientRoutes()


@router.get("")
def get_clients(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")
) -> dict:
    """
    Endpoint που επιστρέφει όλους τους clients.
    """

    require_admin_token(x_admin_token)
    return client_routes.get_clients()


@router.post("/test")
def create_test_client(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")
) -> dict:
    """
    Endpoint που δημιουργεί έναν test client για έλεγχο Supabase.
    """

    require_admin_token(x_admin_token)
    return client_routes.create_test_client()


@router.delete("/test")
def delete_test_client(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")
) -> dict:
    """
    Endpoint που διαγράφει τον test client.
    """

    require_admin_token(x_admin_token)
    return client_routes.delete_test_client()