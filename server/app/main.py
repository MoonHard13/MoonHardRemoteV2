import logging
from fastapi import FastAPI

from app.config import AppConfig
from app.logger_config import LoggerConfig
from app.routes.health_routes import router as health_router
from app.routes.client_routes import router as client_router
from app.routes.websocket_routes import router as websocket_router, websocket_routes
from app.routes.update_routes import router as update_router
from app.websocket.database_duplicate_mark_extension import install_database_duplicate_mark_extension
from app.websocket.registry_extension import install_registry_extension


LoggerConfig.setup_logging()

logger = logging.getLogger(__name__)
config = AppConfig()
config.validate_security_config()

# Επεκτείνουμε το υπάρχον DatabaseRequestRouter με την allowlisted
# Διαγραφή διπλών ΜΑΡΚ και step-level progress.
install_database_duplicate_mark_extension(websocket_routes)

# Εγκαθιστούμε το Registry protocol πάνω στο υπάρχον WebSocketRoutes instance
# χωρίς να αλλάζουμε το μεγάλο legacy routing file.
install_registry_extension(websocket_routes)


class MoonHardServerApp:
    """
    Κεντρική κλάση δημιουργίας του FastAPI server.
    """

    def __init__(self) -> None:
        """
        Δημιουργεί και ρυθμίζει το FastAPI application.
        """

        self.app = FastAPI(
            title=config.app_name,
            version=config.app_version
        )

        self._register_routes()

    def _register_routes(self) -> None:
        """
        Δηλώνει όλα τα routes του FastAPI application.
        """

        self.app.include_router(health_router)
        self.app.include_router(client_router)
        self.app.include_router(websocket_router)
        self.app.include_router(update_router)
        
        logger.info("Server routes registered successfully.")


server_app = MoonHardServerApp()
app = server_app.app


@app.on_event("startup")
async def on_startup() -> None:
    """
    Εκτελείται όταν ξεκινάει ο server.
    """

    logger.info("%s started successfully.", config.app_name)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """
    Εκτελείται όταν κλείνει ο server.
    """

    logger.info("%s stopped.", config.app_name)
