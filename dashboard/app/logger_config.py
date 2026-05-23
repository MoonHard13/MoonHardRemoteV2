import logging
import sys
from pathlib import Path


class DashboardLoggerConfig:
    """
    Κεντρική κλάση ρύθμισης logging για το dashboard.
    """

    @staticmethod
    def setup_logging(log_dir: Path) -> None:
        """
        Ρυθμίζει logging σε αρχείο και κονσόλα.
        """

        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "dashboard.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout)
            ]
        )