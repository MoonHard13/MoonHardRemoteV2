import argparse
import logging
import shutil
import subprocess
import time
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

    def run_command(self, command: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """
        Εκτελεί εντολή συστήματος και επιστρέφει το αποτέλεσμα.
        """

        self.logger.info("Running command: %s", " ".join(command))

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False
        )

        if completed.stdout:
            self.logger.info("Command stdout: %s", completed.stdout.strip())

        if completed.stderr:
            self.logger.warning("Command stderr: %s", completed.stderr.strip())

        return completed

    def stop_service(self) -> None:
        """
        Σταματάει το MoonHard client service.
        """

        self.logger.info("Stopping service: %s", self.config.service_name)

        self.run_command(
            ["sc", "stop", self.config.service_name],
            timeout=60
        )

        for _attempt in range(30):
            if self.get_service_state() == "STOPPED":
                self.logger.info("Service stopped successfully.")
                return

            time.sleep(1)

        raise RuntimeError("Service did not stop within timeout.")

    def start_service(self) -> None:
        """
        Ξεκινάει το MoonHard client service.
        """

        self.logger.info("Starting service: %s", self.config.service_name)

        completed = self.run_command(
            ["sc", "start", self.config.service_name],
            timeout=60
        )

        if completed.returncode not in (0, 1056):
            raise RuntimeError(
                f"Failed to start service. Return code: {completed.returncode}"
            )

        for _attempt in range(30):
            if self.get_service_state() == "RUNNING":
                self.logger.info("Service started successfully.")
                return

            time.sleep(1)

        raise RuntimeError("Service did not start within timeout.")

    def get_service_state(self) -> str:
        """
        Επιστρέφει την τρέχουσα κατάσταση του Windows service.
        """

        completed = self.run_command(
            ["sc", "query", self.config.service_name],
            timeout=30
        )

        output = f"{completed.stdout}\n{completed.stderr}".upper()

        if "RUNNING" in output:
            return "RUNNING"

        if "STOPPED" in output:
            return "STOPPED"

        if "STOP_PENDING" in output:
            return "STOP_PENDING"

        if "START_PENDING" in output:
            return "START_PENDING"

        return "UNKNOWN"

    def replace_installed_files(self, extracted_path: Path) -> None:
        """
        Αντικαθιστά τα installed client αρχεία με τα extracted update αρχεία.
        """

        self.logger.info(
            "Replacing installed files from %s to %s",
            extracted_path,
            self.config.install_dir
        )

        protected_items = {
            "MoonHardRemoteClientService.exe",
            "MoonHardRemoteClientService.xml",
            "MoonHardUpdater.exe",
            "unins000.exe",
            "unins000.dat"
        }

        for item in self.config.install_dir.iterdir():
            if item.name in protected_items:
                self.logger.info("Keeping protected item: %s", item)
                continue

            if item.is_dir():
                self.logger.info("Removing directory: %s", item)
                shutil.rmtree(item)

            else:
                self.logger.info("Removing file: %s", item)
                item.unlink()

        for source_item in extracted_path.iterdir():
            destination_item = self.config.install_dir / source_item.name

            if source_item.is_dir():
                self.logger.info("Copying directory: %s -> %s", source_item, destination_item)
                shutil.copytree(source_item, destination_item)

            else:
                self.logger.info("Copying file: %s -> %s", source_item, destination_item)
                shutil.copy2(source_item, destination_item)

        self.logger.info("Installed files replaced successfully.")

    def rollback_from_backup(self, backup_path: Path) -> None:
        """
        Επαναφέρει τα installed client αρχεία από backup σε περίπτωση αποτυχίας update.
        """

        self.logger.warning("Starting rollback from backup: %s", backup_path)

        if not backup_path.exists() or not backup_path.is_dir():
            raise FileNotFoundError(f"Backup path not found: {backup_path}")

        protected_items = {
            "MoonHardRemoteClientService.exe",
            "MoonHardRemoteClientService.xml",
            "MoonHardUpdater.exe",
            "unins000.exe",
            "unins000.dat"
        }

        for item in self.config.install_dir.iterdir():
            if item.name in protected_items:
                self.logger.info("Keeping protected item during rollback: %s", item)
                continue

            if item.is_dir():
                self.logger.info("Removing directory during rollback: %s", item)
                shutil.rmtree(item)

            else:
                self.logger.info("Removing file during rollback: %s", item)
                item.unlink()

        for backup_item in backup_path.iterdir():
            if backup_item.name in protected_items:
                self.logger.info("Skipping protected backup item: %s", backup_item)
                continue

            destination_item = self.config.install_dir / backup_item.name

            if backup_item.is_dir():
                self.logger.info("Restoring directory: %s -> %s", backup_item, destination_item)
                shutil.copytree(backup_item, destination_item)

            else:
                self.logger.info("Restoring file: %s -> %s", backup_item, destination_item)
                shutil.copy2(backup_item, destination_item)

        self.logger.warning("Rollback completed successfully.")

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
    def run_apply(self, extracted_path: Path) -> dict:
        """
        Εκτελεί πραγματικό update του installed client με rollback σε περίπτωση αποτυχίας.
        """

        self.logger.info("Starting updater apply mode.")
        self.logger.info("Extracted path: %s", extracted_path)

        backup_path: Path | None = None
        rollback_performed = False

        self.validate_extracted_package(extracted_path)
        self.validate_installation_folder()

        self.stop_service()

        backup_path = self.create_backup()

        try:
            self.replace_installed_files(extracted_path)
            self.start_service()

        except Exception as exc:
            self.logger.exception("Apply update failed. Starting rollback.")

            try:
                if backup_path:
                    self.rollback_from_backup(backup_path)
                    rollback_performed = True

                self.start_service()

            except Exception:
                self.logger.exception("Rollback failed or service failed to start after rollback.")

            raise RuntimeError(
                f"Apply update failed. Rollback performed: {rollback_performed}. "
                f"Original error: {exc}"
            ) from exc

        result = {
            "success": True,
            "mode": "apply",
            "extracted_path": str(extracted_path),
            "install_dir": str(self.config.install_dir),
            "backup_path": str(backup_path),
            "rollback_performed": rollback_performed,
            "message": "Update applied successfully."
        }

        self.logger.info("Apply update completed successfully.")

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
        choices=["prepare-only", "apply"],
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

        elif args.mode == "apply":
            result = runner.run_apply(
                extracted_path=Path(args.extracted_path)
            )

        else:
            raise ValueError(f"Unsupported mode: {args.mode}")

        logger.info("Updater result: %s", result)

    except Exception:
        logger.exception("Updater failed.")
        raise


if __name__ == "__main__":
    main()