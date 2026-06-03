import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path

from app.updater_config import UpdaterConfig


class MoonHardUpdateRunner:
    """
    Εκτελεί ασφαλείς εργασίες προετοιμασίας update για τον MoonHard Remote Client.
    """

    def __init__(self, config: UpdaterConfig) -> None:
        """
        Αρχικοποιεί τον updater runner.
        """

        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate_extracted_package(self, extracted_path: Path) -> None:
        """
        Ελέγχει ότι το extracted package περιέχει τα απαραίτητα αρχεία.
        """

        if not extracted_path.exists() or not extracted_path.is_dir():
            raise FileNotFoundError(f"Extracted path not found: {extracted_path}")

        missing_items: list[str] = []

        for item_name in self.config.required_items:
            item_path = extracted_path / item_name

            if not item_path.exists():
                missing_items.append(item_name)

        if missing_items:
            raise RuntimeError(
                "Extracted package is missing required items: "
                + ", ".join(missing_items)
            )

        self.logger.info("Extracted package validation passed: %s", extracted_path)

    def validate_installation_folder(self) -> None:
        """
        Ελέγχει ότι υπάρχει ο εγκατεστημένος client.
        """

        if not self.config.install_dir.exists():
            raise FileNotFoundError(
                f"Client install folder not found: {self.config.install_dir}"
            )

        client_exe = self.config.install_dir / self.config.client_exe_name

        if not client_exe.exists():
            raise FileNotFoundError(
                f"Client executable not found: {client_exe}"
            )

        self.logger.info("Installation folder validation passed: %s", self.config.install_dir)

    def create_backup(self) -> Path:
        """
        Δημιουργεί backup του τρέχοντος installed client folder.
        """

        self.config.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config.backup_dir / f"client_backup_{timestamp}"

        self.logger.info("Creating backup from %s to %s", self.config.install_dir, backup_path)

        shutil.copytree(
            self.config.install_dir,
            backup_path,
            dirs_exist_ok=False
        )

        self.logger.info("Backup completed: %s", backup_path)

        return backup_path

    def run_prepare_only(self, extracted_path: Path) -> dict:
        """
        Εκτελεί μόνο validation και backup χωρίς αντικατάσταση αρχείων.
        """

        self.logger.info("Starting updater prepare-only mode.")
        self.logger.info("Extracted path: %s", extracted_path)

        self.validate_extracted_package(extracted_path)
        self.validate_installation_folder()

        backup_path = self.create_backup()

        result = {
            "success": True,
            "mode": "prepare-only",
            "extracted_path": str(extracted_path),
            "install_dir": str(self.config.install_dir),
            "backup_path": str(backup_path),
            "message": "Prepare-only completed. No files were replaced."
        }

        self.logger.info("Prepare-only completed successfully.")

        return result


def setup_logging(config: UpdaterConfig) -> None:
    """
    Ρυθμίζει logging για τον updater.
    """

    config.logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = config.logs_dir / "moonhard_updater.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def parse_args() -> argparse.Namespace:
    """
    Διαβάζει arguments από command line.
    """

    parser = argparse.ArgumentParser(
        description="MoonHard Remote Client external updater."
    )

    parser.add_argument(
        "--mode",
        choices=["prepare-only"],
        required=True,
        help="Updater execution mode."
    )

    parser.add_argument(
        "--extracted-path",
        required=True,
        help="Path to extracted update package."
    )

    return parser.parse_args()


def main() -> None:
    """
    Entry point του updater.
    """

    config = UpdaterConfig()
    setup_logging(config)

    logger = logging.getLogger("MoonHardUpdaterMain")

    try:
        args = parse_args()

        runner = MoonHardUpdateRunner(config=config)

        if args.mode == "prepare-only":
            result = runner.run_prepare_only(
                extracted_path=Path(args.extracted_path)
            )

            logger.info("Updater result: %s", result)

    except Exception:
        logger.exception("Updater failed.")
        raise


if __name__ == "__main__":
    main()