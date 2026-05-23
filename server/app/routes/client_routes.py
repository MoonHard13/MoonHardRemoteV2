import logging
from fastapi import APIRouter, HTTPException

from app.repositories.client_repository import ClientRepository


router = APIRouter(prefix="/api/clients", tags=["Clients"])
logger = logging.getLogger(__name__)


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
        """

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
        """

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
def get_clients() -> dict:
    """
    Endpoint που επιστρέφει όλους τους clients.
    """

    return client_routes.get_clients()


@router.post("/test")
def create_test_client() -> dict:
    """
    Endpoint που δημιουργεί έναν test client για έλεγχο Supabase.
    """

    return client_routes.create_test_client()


@router.delete("/test")
def delete_test_client() -> dict:
    """
    Endpoint που διαγράφει τον test client.
    """

    return client_routes.delete_test_client()