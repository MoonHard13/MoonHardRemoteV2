import logging
import sys


class LoggerConfig:
    """
    Κεντρική κλάση ρύθμισης logging για τον server.
    """

    @staticmethod
    def setup_logging() -> None:
        """
        Ρυθμίζει το logging ώστε να εμφανίζεται καθαρά στο console.
        """

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )