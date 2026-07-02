import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ClientLoggerConfig:
    """
    Κεντρική κλάση ρύθμισης logging για τον client.
    """

    @staticmethod
    def setup_logging(log_dir: Path) -> None:
        """
        Ρυθμίζει logging σε αρχείο και κονσόλα με rotation.
<<<<<<< HEAD

        Αν θέλουμε να βλέπουμε INFO logs στο terminal για debugging,
        βάζουμε στο περιβάλλον:
        MOONHARD_CLIENT_CONSOLE_LOG_LEVEL=INFO
=======
>>>>>>> 77778894ab898cbaa6982bfcc559e19f4b6b601e
        """

        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "client.log"

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

<<<<<<< HEAD
        console_level_name = os.getenv(
            "MOONHARD_CLIENT_CONSOLE_LOG_LEVEL",
            "WARNING"
        ).strip().upper()

        console_level = getattr(
            logging,
            console_level_name,
            logging.WARNING
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(console_level)
=======
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.WARNING)
>>>>>>> 77778894ab898cbaa6982bfcc559e19f4b6b601e
        stream_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)

        logging.getLogger("websockets").setLevel(logging.WARNING)
<<<<<<< HEAD
        logging.getLogger("websocket").setLevel(logging.WARNING)
=======
        logging.getLogger("websocket").setLevel(logging.WARNING)
>>>>>>> 77778894ab898cbaa6982bfcc559e19f4b6b601e
