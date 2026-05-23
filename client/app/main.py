import asyncio
import logging

from app.config import ClientConfig
from app.logger_config import ClientLoggerConfig
from app.client_agent import MoonHardClientAgent


def main() -> None:
    """
    Κεντρικό σημείο εκκίνησης του MoonHard Remote Client.
    """

    config = ClientConfig()
    ClientLoggerConfig.setup_logging(config.log_dir)

    logger = logging.getLogger(__name__)
    logger.info("Εκκίνηση MoonHard Remote v2 Client.")

    agent = MoonHardClientAgent()

    asyncio.run(agent.run_forever())


if __name__ == "__main__":
    main()