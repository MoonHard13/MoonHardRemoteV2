import logging
from fastapi import FastAPI

from app.config import AppConfig
from app.logger_config import LoggerConfig
from app.routes.health_routes import router as health_router


LoggerConfig.setup_logging()

logger = logging.getLogger(__name__)
config = AppConfig()


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
        Δηλώνει όλα τα routes του server.
        """

        self.app.include_router(health_router)
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