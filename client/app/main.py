import asyncio
import logging
import sys

from app.config import ClientConfig
from app.logger_config import ClientLoggerConfig


def main() -> None:
    """
    Κεντρικό σημείο εκκίνησης του MoonHard Remote Client.
    """

    if len(sys.argv) == 3 and sys.argv[1] == "--terminal-self-test":
        from app.terminal_smoke import ClientTerminalSmokeTest
        raise SystemExit(asyncio.run(ClientTerminalSmokeTest.run(sys.argv[2])))

    config = ClientConfig()
    ClientLoggerConfig.setup_logging(config.log_dir)

    logger = logging.getLogger(__name__)
    logger.info("Εκκίνηση MoonHard Remote v2 Client.")

    from app.client_agent import MoonHardClientAgent
    agent = MoonHardClientAgent()

    asyncio.run(agent.run_forever())


if __name__ == "__main__":
    main()