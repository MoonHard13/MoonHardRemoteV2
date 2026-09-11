import calendar
import hashlib
import json
import logging
import ntpath
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import pyodbc

logger = logging.getLogger(__name__)


class BackupValidationError(ValueError):
    """Σφάλμα ελέγχου ρυθμίσεων backup ή schedule."""


class BackupSettingsValidator:
    """Ελέγχει και κανονικοποιεί όλες τις ρυθμίσεις πριν χρησιμοποιηθούν."""

    DESTINATION_TYPES: ClassVar[frozenset[str]] = frozenset({"local", "unc", "cloud"})
    RETENTION_MODES: ClassVar[frozenset[str]] = frozenset(
        {"replace", "keep_all", "keep_last"}
    )
    FREQUENCIES: ClassVar[frozenset[str]] = frozenset({"daily", "weekly", "monthly"})

    @classmethod
    def backup_settings(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Επιστρέφει ασφαλείς ρυθμίσεις προορισμού και πολιτικής διατήρησης."""

        if not isinstance(values, dict):
            raise BackupValidationError("Backup settings must be an object.")

        destination_type = cls._choice(
            values.get("destination_type"),
            cls.DESTINATION_TYPES,
            "destination_type",
        )
        retention_mode = cls._choice(
            values.get("retention_mode", "keep_last"),
            cls.RETENTION_MODES,
            "retention_mode",
        )
        retention_count = cls._integer(
            values.get("retention_count", 7),
            "retention_count",
            1,
            365,
        )

        normalized: dict[str, Any] = {
            "destination_type": destination_type,
            "destination_path": "",
            "staging_path": "",
            "cloud_remote": "",
            "retention_mode": retention_mode,
            "retention_count": retention_count,
            "compression": cls._boolean(values.get("compression", True), "compression"),
            "copy_only": cls._boolean(values.get("copy_only", True), "copy_only"),
        }

        if destination_type in {"local", "unc"}:
            destination_path = cls._windows_path(
                values.get("destination_path"),
                "destination_path",
            )
            if destination_type == "unc" and not destination_path.startswith("\\\\"):
                raise BackupValidationError(
                    "UNC destination must start with \\\\server\\share."
                )
            if destination_type == "local" and destination_path.startswith("\\\\"):
                raise BackupValidationError(
                    "Local destination must use an absolute drive path."
                )
            normalized["destination_path"] = destination_path
        else:
            normalized["staging_path"] = cls._windows_path(
                values.get("staging_path"),
                "staging_path",
            )
            normalized["cloud_remote"] = cls._cloud_remote(values.get("cloud_remote"))

        return normalized

    @classmethod
    def schedule(
        cls,
        values: dict[str, Any],
        existing: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Ελέγχει schedule και υπολογίζει την επόμενη τοπική εκτέλεση."""

        if not isinstance(values, dict):
            raise BackupValidationError("Schedule must be an object.")

        current = existing if isinstance(existing, dict) else {}
        raw_id = str(values.get("schedule_id") or current.get("schedule_id") or "")
        try:
            schedule_id = str(uuid.UUID(raw_id)) if raw_id else str(uuid.uuid4())
        except ValueError as exc:
            raise BackupValidationError("Invalid schedule_id.") from exc

        name = cls._text(values.get("name"), "name", 1, 80)
        bo_connection_id = cls._integer(
            values.get("bo_connection_id"),
            "bo_connection_id",
            1,
            2147483647,
        )
        frequency = cls._choice(values.get("frequency"), cls.FREQUENCIES, "frequency")
        run_time = cls._time(values.get("time"))
        weekday = cls._integer(values.get("weekday", 0), "weekday", 0, 6)
        day_of_month = cls._integer(
            values.get("day_of_month", 1), "day_of_month", 1, 31
        )
        enabled = cls._boolean(values.get("enabled", True), "enabled")
        settings = cls.backup_settings(values.get("settings", {}))

        schedule = {
            "schedule_id": schedule_id,
            "name": name,
            "bo_connection_id": bo_connection_id,
            "frequency": frequency,
            "time": run_time,
            "weekday": weekday,
            "day_of_month": day_of_month,
            "enabled": enabled,
            "settings": settings,
            "created_at": str(current.get("created_at") or cls._now_iso()),
            "updated_at": cls._now_iso(),
            "last_started_at": current.get("last_started_at"),
            "last_finished_at": current.get("last_finished_at"),
            "last_status": current.get("last_status"),
            "last_message": current.get("last_message"),
        }
        schedule["next_run_at"] = (
            cls.next_run(schedule, now=now).isoformat() if enabled else None
        )
        return schedule

    @classmethod
    def next_run(
        cls, schedule: dict[str, Any], now: datetime | None = None
    ) -> datetime:
        """Υπολογίζει την αμέσως επόμενη εκτέλεση στην τοπική ζώνη ώρας."""

        local_now = now or datetime.now().astimezone()
        if local_now.tzinfo is None:
            local_now = local_now.astimezone()
        hour, minute = (int(part) for part in str(schedule["time"]).split(":"))
        frequency = str(schedule["frequency"])

        if frequency == "daily":
            candidate = local_now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return candidate if candidate > local_now else candidate + timedelta(days=1)

        if frequency == "weekly":
            days_ahead = (int(schedule["weekday"]) - local_now.weekday()) % 7
            candidate = (local_now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return candidate if candidate > local_now else candidate + timedelta(days=7)

        year = local_now.year
        month = local_now.month
        for _ in range(14):
            last_day = calendar.monthrange(year, month)[1]
            day = min(int(schedule["day_of_month"]), last_day)
            candidate = local_now.replace(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            if candidate > local_now:
                return candidate
            month += 1
            if month == 13:
                month = 1
                year += 1
        raise BackupValidationError("Unable to calculate the next schedule run.")

    @staticmethod
    def public_settings(values: dict[str, Any]) -> dict[str, Any]:
        """Επιστρέφει αντίγραφο ρυθμίσεων χωρίς δυνατότητα μεταβολής του store."""

        return deepcopy(values)

    @staticmethod
    def _choice(value: Any, allowed: frozenset[str], field: str) -> str:
        clean = str(value or "").strip().lower()
        if clean not in allowed:
            raise BackupValidationError(f"Invalid {field}.")
        return clean

    @staticmethod
    def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise BackupValidationError(f"Invalid {field}.")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise BackupValidationError(f"Invalid {field}.") from exc
        if not minimum <= number <= maximum:
            raise BackupValidationError(
                f"{field} must be between {minimum} and {maximum}."
            )
        return number

    @staticmethod
    def _boolean(value: Any, field: str) -> bool:
        if type(value) is not bool:
            raise BackupValidationError(f"Invalid {field}.")
        return value

    @staticmethod
    def _text(value: Any, field: str, minimum: int, maximum: int) -> str:
        if not isinstance(value, str):
            raise BackupValidationError(f"Invalid {field}.")
        clean = value.strip()
        if not minimum <= len(clean) <= maximum or any(
            ord(char) < 32 for char in clean
        ):
            raise BackupValidationError(f"Invalid {field}.")
        return clean

    @classmethod
    def _windows_path(cls, value: Any, field: str) -> str:
        clean = cls._text(value, field, 3, 1024)
        if '"' in clean or "\x00" in clean:
            raise BackupValidationError(f"Invalid {field}.")
        if not (re.match(r"^[A-Za-z]:[\\/]", clean) or clean.startswith("\\\\")):
            raise BackupValidationError(
                f"{field} must be an absolute Windows or UNC path."
            )
        return ntpath.normpath(clean)

    @classmethod
    def _cloud_remote(cls, value: Any) -> str:
        clean = cls._text(value, "cloud_remote", 3, 512).replace("\\", "/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}:[^\x00-\x1f]*", clean):
            raise BackupValidationError(
                "Cloud remote must use rclone format, for example mega:MoonHardBackups."
            )
        remote_path = clean.split(":", 1)[1]
        if any(part == ".." for part in remote_path.split("/")):
            raise BackupValidationError(
                "Cloud remote cannot contain '..' path segments."
            )
        return clean.rstrip("/")

    @staticmethod
    def _time(value: Any) -> str:
        clean = str(value or "").strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clean):
            raise BackupValidationError(
                "Schedule time must use HH:MM (24-hour format)."
            )
        return clean

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat()


class BackupStateStore:
    """Αποθηκεύει schedules και ιστορικό τοπικά με atomic JSON writes."""

    VERSION = 1

    def __init__(self, state_file: Path, history_limit: int = 500) -> None:
        self.state_file = Path(state_file)
        self.backup_file = self.state_file.with_suffix(self.state_file.suffix + ".bak")
        self.history_limit = max(50, min(int(history_limit), 5000))
        self._lock = threading.RLock()

    def snapshot(self) -> dict[str, Any]:
        """Επιστρέφει ταξινομημένο αντίγραφο του τρέχοντος state."""

        with self._lock:
            state = self._load_unlocked()
            schedules = sorted(
                state["schedules"], key=lambda item: str(item.get("name", "")).lower()
            )
            history = sorted(
                state["history"],
                key=lambda item: str(item.get("started_at", "")),
                reverse=True,
            )
            return {"schedules": deepcopy(schedules), "history": deepcopy(history)}

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        """Επιστρέφει schedule βάσει ID."""

        with self._lock:
            state = self._load_unlocked()
            item = next(
                (
                    schedule
                    for schedule in state["schedules"]
                    if schedule.get("schedule_id") == schedule_id
                ),
                None,
            )
            return deepcopy(item) if item else None

    def save_schedule(self, values: dict[str, Any]) -> dict[str, Any]:
        """Δημιουργεί ή ενημερώνει ένα πλήρως ελεγμένο schedule."""

        with self._lock:
            state = self._load_unlocked()
            raw_id = str(values.get("schedule_id") or "")
            existing = next(
                (
                    item
                    for item in state["schedules"]
                    if item.get("schedule_id") == raw_id
                ),
                None,
            )
            schedule = BackupSettingsValidator.schedule(values, existing=existing)
            state["schedules"] = [
                item
                for item in state["schedules"]
                if item.get("schedule_id") != schedule["schedule_id"]
            ]
            state["schedules"].append(schedule)
            self._write_unlocked(state)
            return deepcopy(schedule)

    def delete_schedule(self, schedule_id: str) -> bool:
        """Διαγράφει μόνο το schedule που αντιστοιχεί στο έγκυρο UUID."""

        try:
            clean_id = str(uuid.UUID(str(schedule_id)))
        except ValueError as exc:
            raise BackupValidationError("Invalid schedule_id.") from exc

        with self._lock:
            state = self._load_unlocked()
            original_count = len(state["schedules"])
            state["schedules"] = [
                item
                for item in state["schedules"]
                if item.get("schedule_id") != clean_id
            ]
            deleted = len(state["schedules"]) != original_count
            if deleted:
                self._write_unlocked(state)
            return deleted

    def claim_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Δεσμεύει due schedules πριν την εκτέλεση για αποφυγή διπλού run."""

        local_now = now or datetime.now().astimezone()
        claimed: list[dict[str, Any]] = []
        with self._lock:
            state = self._load_unlocked()
            changed = False
            for schedule in state["schedules"]:
                if not schedule.get("enabled") or not schedule.get("next_run_at"):
                    continue
                try:
                    next_run = datetime.fromisoformat(str(schedule["next_run_at"]))
                except ValueError:
                    next_run = local_now
                if next_run.tzinfo is None:
                    next_run = next_run.astimezone()
                if next_run > local_now:
                    continue
                schedule["last_started_at"] = local_now.isoformat()
                schedule["next_run_at"] = BackupSettingsValidator.next_run(
                    schedule, now=local_now
                ).isoformat()
                claimed.append(deepcopy(schedule))
                changed = True
            if changed:
                self._write_unlocked(state)
        return claimed

    def record_schedule_result(
        self, schedule_id: str, status: str, message: str
    ) -> None:
        """Ενημερώνει την τελευταία κατάσταση schedule χωρίς να αλλάζει το next run."""

        with self._lock:
            state = self._load_unlocked()
            for schedule in state["schedules"]:
                if schedule.get("schedule_id") == schedule_id:
                    schedule["last_finished_at"] = (
                        datetime.now().astimezone().isoformat()
                    )
                    schedule["last_status"] = str(status)[:32]
                    schedule["last_message"] = str(message)[:1000]
                    self._write_unlocked(state)
                    return

    def append_history(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Προσθέτει ασφαλές history item και κρατά το καθορισμένο όριο."""

        item = deepcopy(entry)
        item["history_id"] = str(item.get("history_id") or uuid.uuid4())
        with self._lock:
            state = self._load_unlocked()
            state["history"].insert(0, item)
            state["history"] = state["history"][: self.history_limit]
            self._write_unlocked(state)
        return deepcopy(item)

    def retryable_uploads(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Επιστρέφει cloud uploads που μπορούν να επαναληφθούν χωρίς νέο SQL backup."""

        local_now = now or datetime.now().astimezone()
        with self._lock:
            state = self._load_unlocked()
            result: list[dict[str, Any]] = []
            for entry in state["history"]:
                if entry.get("status") != "upload_failed":
                    continue
                if int(entry.get("retry_count", 0)) >= 5:
                    continue
                retry_at_text = str(entry.get("next_retry_at") or "")
                try:
                    retry_at = datetime.fromisoformat(retry_at_text)
                except ValueError:
                    retry_at = local_now
                if retry_at.tzinfo is None:
                    retry_at = retry_at.astimezone()
                if retry_at <= local_now:
                    result.append(deepcopy(entry))
            return result

    def update_history(
        self, history_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Ενημερώνει συγκεκριμένο history item."""

        with self._lock:
            state = self._load_unlocked()
            for entry in state["history"]:
                if entry.get("history_id") == history_id:
                    entry.update(deepcopy(changes))
                    self._write_unlocked(state)
                    return deepcopy(entry)
        return None

    def _load_unlocked(self) -> dict[str, Any]:
        """Διαβάζει το state και χρησιμοποιεί το last-good αντίγραφο αν χρειαστεί."""

        default = {"version": self.VERSION, "schedules": [], "history": []}
        if not self.state_file.exists():
            return default
        for candidate in (self.state_file, self.backup_file):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if (
                    isinstance(data, dict)
                    and isinstance(data.get("schedules"), list)
                    and isinstance(data.get("history"), list)
                ):
                    return {
                        "version": self.VERSION,
                        "schedules": data["schedules"],
                        "history": data["history"],
                    }
            except (OSError, ValueError, TypeError):
                logger.exception("Αποτυχία ανάγνωσης backup state: %s", candidate)
        raise RuntimeError(
            "Backup schedules storage is damaged and cannot be recovered."
        )

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        """Γράφει το JSON atomically και διατηρεί προηγούμενο last-good αρχείο."""

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self.state_file.exists():
            shutil.copy2(self.state_file, self.backup_file)
        os.replace(temporary, self.state_file)


class RcloneCloudAdapter:
    """Εκτελεί ελεγχόμενες rclone εντολές χωρίς shell ή απομακρυσμένο executable path."""

    def __init__(self, executable: str, config_file: Path) -> None:
        self.executable = str(executable)
        self.config_file = Path(config_file)

    def list_remotes(self) -> list[str]:
        """Επιστρέφει μόνο τα ονόματα των locally configured rclone remotes."""

        output = self._run_capture(["listremotes"], timeout=60)
        return sorted(
            {
                line.strip().rstrip(":")
                for line in output.splitlines()
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}:", line.strip())
            }
        )

    def upload(
        self,
        local_file: str,
        cloud_remote: str,
        database_token: str,
        retention_mode: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, int]:
        """Ανεβάζει αρχείο και επιβεβαιώνει το τελικό remote size."""

        local_size = os.path.getsize(local_file)
        original_name = ntpath.basename(local_file)
        final_name = (
            f"{database_token}_latest.bak"
            if retention_mode == "replace"
            else original_name
        )
        final_remote = self._remote_join(cloud_remote, final_name)
        upload_remote = (
            f"{final_remote}.uploading-{uuid.uuid4().hex[:8]}"
            if retention_mode == "replace"
            else final_remote
        )

        self._run_stream(
            [
                "copyto",
                local_file,
                upload_remote,
                "--transfers",
                "1",
                "--checkers",
                "2",
                "--retries",
                "3",
                "--low-level-retries",
                "10",
                "--stats",
                "2s",
                "--stats-one-line",
            ],
            progress_callback=progress_callback,
            timeout=14400,
        )
        uploaded_size = self._remote_size(upload_remote)
        if uploaded_size != local_size:
            raise RuntimeError(
                f"Cloud verification failed: local={local_size} bytes, remote={uploaded_size} bytes."
            )

        if upload_remote != final_remote:
            self._run_capture(["moveto", upload_remote, final_remote], timeout=3600)
            uploaded_size = self._remote_size(final_remote)
            if uploaded_size != local_size:
                raise RuntimeError(
                    "Cloud replacement verification failed after final move."
                )

        return final_remote, uploaded_size

    def enforce_keep_last(
        self,
        cloud_remote: str,
        database_token: str,
        keep_count: int,
    ) -> list[str]:
        """Διαγράφει μόνο παλαιότερα timestamped backups του ίδιου database token."""

        output = self._run_capture(
            ["lsjson", cloud_remote, "--files-only", "--max-depth", "1"],
            timeout=300,
        )
        try:
            items = json.loads(output)
        except ValueError as exc:
            raise RuntimeError(
                "rclone returned invalid JSON while applying retention."
            ) from exc
        pattern = re.compile(
            rf"^{re.escape(database_token)}_\d{{8}}_\d{{6}}_\d{{3}}\.bak$",
            re.IGNORECASE,
        )
        candidates = [
            item
            for item in items
            if isinstance(item, dict) and pattern.fullmatch(str(item.get("Name") or ""))
        ]
        candidates.sort(
            key=lambda item: (
                str(item.get("ModTime") or ""),
                str(item.get("Name") or ""),
            ),
            reverse=True,
        )
        deleted: list[str] = []
        for item in candidates[keep_count:]:
            remote_file = self._remote_join(cloud_remote, str(item["Name"]))
            self._run_capture(["deletefile", remote_file], timeout=300)
            deleted.append(str(item["Name"]))
        return deleted

    def _remote_size(self, remote_file: str) -> int:
        output = self._run_capture(["size", remote_file, "--json"], timeout=300)
        try:
            data = json.loads(output)
            return int(data.get("bytes", -1))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RuntimeError(
                "rclone could not verify the uploaded file size."
            ) from exc

    def _command(self, arguments: list[str]) -> list[str]:
        executable = self._resolve_executable()
        if not self.config_file.is_file():
            raise RuntimeError(
                f"rclone configuration was not found at {self.config_file}."
            )
        return [executable, *arguments, "--config", str(self.config_file)]

    def _resolve_executable(self) -> str:
        configured = Path(self.executable)
        if configured.is_file():
            return str(configured)
        found = shutil.which(self.executable)
        if found:
            return found
        raise RuntimeError(
            "rclone was not found. Install it or place rclone.exe in the configured client folder."
        )

    def _run_capture(self, arguments: list[str], timeout: int) -> str:
        completed = subprocess.run(
            self._command(arguments),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "rclone failed.").strip()
            raise RuntimeError(detail[-2000:])
        return completed.stdout.strip()

    def _run_stream(
        self,
        arguments: list[str],
        progress_callback: Callable[[dict[str, Any]], None] | None,
        timeout: int,
    ) -> None:
        process = subprocess.Popen(
            self._command(arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        started = time.monotonic()
        output_tail: list[str] = []
        assert process.stdout is not None

        line_queue: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            """Διαβάζει stdout χωρίς να μπλοκάρει τον έλεγχο συνολικού timeout."""

            try:
                for output_line in process.stdout:
                    line_queue.put(output_line)
            finally:
                line_queue.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            while True:
                if time.monotonic() - started > timeout:
                    process.kill()
                    raise TimeoutError("Cloud upload timed out.")
                try:
                    line = line_queue.get(timeout=1)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                clean = line.strip()
                if clean:
                    output_tail.append(clean)
                    output_tail = output_tail[-20:]
                    if progress_callback:
                        progress_callback(
                            {"stage": "cloud_upload", "message": clean[:1000]}
                        )
            return_code = process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
        if return_code != 0:
            raise RuntimeError(
                "\n".join(output_tail)[-2000:] or "rclone upload failed."
            )

    @staticmethod
    def _remote_join(remote: str, file_name: str) -> str:
        return remote.rstrip("/") + "/" + file_name


class SqlServerBackupService:
    """Δημιουργεί, επαληθεύει, ανεβάζει και καθαρίζει SQL Server full backups."""

    def __init__(self, cloud_adapter: RcloneCloudAdapter) -> None:
        self.cloud_adapter = cloud_adapter
        self._active_databases: set[str] = set()
        self._active_lock = threading.Lock()

    def execute(
        self,
        connection_string: str,
        settings: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Εκτελεί verified backup και εφαρμόζει την επιλεγμένη retention policy."""

        started_at = time.perf_counter()
        try:
            safe_settings = BackupSettingsValidator.backup_settings(settings)
            parsed = self._parse_connection_string(connection_string)
            database_name = parsed.get("database", "")
            if not database_name:
                raise BackupValidationError(
                    "Missing SQL database in connection string."
                )
            database_token = self._safe_database_token(database_name)
            if not self._acquire_database(database_name):
                raise RuntimeError("A backup is already running for this database.")
            try:
                return self._execute_locked(
                    connection_string,
                    database_name,
                    database_token,
                    safe_settings,
                    progress_callback,
                    started_at,
                )
            finally:
                self._release_database(database_name)
        except Exception as exc:
            logger.exception("Αποτυχία database backup.")
            return {
                "success": False,
                "status": "failed",
                "error": self._sanitize_error(str(exc), connection_string),
                "message": "Database backup failed.",
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "verified": False,
                "retryable": False,
            }

    def retry_upload(
        self,
        history_entry: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Επαναλαμβάνει μόνο αποτυχημένο cloud upload από verified staging file."""

        started_at = time.perf_counter()
        try:
            settings = BackupSettingsValidator.backup_settings(
                history_entry.get("settings", {})
            )
            if settings["destination_type"] != "cloud":
                raise BackupValidationError("History entry is not a cloud backup.")
            local_file = str(history_entry.get("staging_file_path") or "")
            database_name = str(history_entry.get("database_name") or "")
            database_token = self._safe_database_token(database_name)
            if not local_file or not os.path.isfile(local_file):
                raise RuntimeError("Verified staging backup is no longer available.")
            self._emit(
                progress_callback, "cloud_upload", "Retrying cloud upload...", 75
            )
            remote_file, remote_size = self.cloud_adapter.upload(
                local_file,
                settings["cloud_remote"],
                database_token,
                settings["retention_mode"],
                progress_callback,
            )
            deleted = self._cloud_retention(settings, database_token)
            os.remove(local_file)
            self._emit(
                progress_callback, "completed", "Cloud upload retry completed.", 100
            )
            return {
                "success": True,
                "status": "completed",
                "message": "Cloud upload retry completed successfully.",
                "remote_file_path": remote_file,
                "size_bytes": remote_size,
                "retention_deleted": deleted,
                "verified": True,
                "retryable": False,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            }
        except Exception as exc:
            logger.exception("Αποτυχία επανάληψης cloud upload.")
            return {
                "success": False,
                "status": "upload_failed",
                "message": "Cloud upload retry failed.",
                "error": str(exc)[:4000],
                "verified": True,
                "retryable": True,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            }

    def _execute_locked(
        self,
        connection_string: str,
        database_name: str,
        database_token: str,
        settings: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None,
        started_at: float,
    ) -> dict[str, Any]:
        folder = (
            settings["staging_path"]
            if settings["destination_type"] == "cloud"
            else settings["destination_path"]
        )
        os.makedirs(folder, exist_ok=True)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:19]
        file_name = f"{database_token}_{timestamp}.bak"
        backup_path = ntpath.join(folder, file_name)
        self._emit(progress_callback, "preparing", "Preparing SQL Server backup...", 1)

        self._run_sql_backup(
            connection_string,
            database_name,
            backup_path,
            settings,
            progress_callback,
        )
        self._emit(
            progress_callback,
            "verifying",
            "Verifying backup with RESTORE VERIFYONLY...",
            92,
        )
        self._verify_backup(connection_string, backup_path)

        client_accessible = os.path.isfile(backup_path)
        warnings: list[str] = []
        size_bytes = os.path.getsize(backup_path) if client_accessible else None
        sha256 = None
        if client_accessible:
            self._emit(progress_callback, "checksum", "Calculating SHA-256...", 95)
            sha256 = self._sha256(backup_path)
        else:
            warnings.append(
                "The SQL backup was verified, but the client service cannot read the backup path."
            )

        if settings["destination_type"] == "cloud":
            if not client_accessible:
                raise RuntimeError(
                    "The client service cannot read the cloud staging file after SQL verification."
                )
            try:
                self._emit(
                    progress_callback,
                    "cloud_upload",
                    "Uploading verified backup to cloud...",
                    96,
                )
                remote_file, remote_size = self.cloud_adapter.upload(
                    backup_path,
                    settings["cloud_remote"],
                    database_token,
                    settings["retention_mode"],
                    progress_callback,
                )
                deleted = self._cloud_retention(settings, database_token)
                os.remove(backup_path)
                self._emit(
                    progress_callback,
                    "completed",
                    "Backup completed and uploaded.",
                    100,
                )
                return {
                    "success": True,
                    "status": "completed",
                    "message": "Database backup completed, verified, and uploaded successfully.",
                    "database_name": database_name,
                    "file_name": ntpath.basename(remote_file),
                    "remote_file_path": remote_file,
                    "staging_file_path": "",
                    "size_bytes": remote_size,
                    "sha256": sha256,
                    "verified": True,
                    "cloud_uploaded": True,
                    "retention_deleted": deleted,
                    "warnings": warnings,
                    "retryable": False,
                    "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                }
            except Exception as exc:
                logger.exception("Cloud upload failed after successful SQL backup.")
                return {
                    "success": False,
                    "status": "upload_failed",
                    "message": "SQL backup is verified, but the cloud upload failed.",
                    "error": str(exc)[:4000],
                    "database_name": database_name,
                    "file_name": file_name,
                    "staging_file_path": backup_path,
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                    "verified": True,
                    "cloud_uploaded": False,
                    "retention_deleted": [],
                    "warnings": warnings,
                    "retryable": True,
                    "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                }

        final_path = backup_path
        deleted: list[str] = []
        if settings["retention_mode"] == "replace":
            if not client_accessible:
                raise RuntimeError(
                    "Replace mode requires the client service to access the destination folder."
                )
            final_path = ntpath.join(folder, f"{database_token}_latest.bak")
            os.replace(backup_path, final_path)
        elif settings["retention_mode"] == "keep_last":
            if client_accessible:
                deleted = self._local_keep_last(
                    folder, database_token, settings["retention_count"]
                )
            else:
                warnings.append(
                    "Retention was skipped because the client cannot read the folder."
                )

        self._emit(
            progress_callback, "completed", "Backup completed and verified.", 100
        )
        return {
            "success": True,
            "status": "completed",
            "message": "Database backup completed and verified successfully.",
            "database_name": database_name,
            "file_name": ntpath.basename(final_path),
            "file_path": final_path,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "verified": True,
            "cloud_uploaded": False,
            "retention_deleted": deleted,
            "warnings": warnings,
            "retryable": False,
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        }

    def _run_sql_backup(
        self,
        connection_string: str,
        database_name: str,
        backup_path: str,
        settings: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        odbc_string = self._to_odbc_connection_string(connection_string)
        ready = threading.Event()
        finished = threading.Event()
        worker_state: dict[str, Any] = {}

        options = ["CHECKSUM", "INIT", "STATS = 5"]
        if settings["copy_only"]:
            options.append("COPY_ONLY")
        if settings["compression"]:
            options.append("COMPRESSION")
        sql = (
            "DECLARE @backup_path nvarchar(4000) = ?; "
            f"BACKUP DATABASE {self._quote_identifier(database_name)} "
            "TO DISK = @backup_path WITH " + ", ".join(options) + ";"
        )

        def worker() -> None:
            """Εκτελεί το blocking BACKUP σε δικό του thread."""

            try:
                with pyodbc.connect(
                    odbc_string, timeout=60, autocommit=True
                ) as connection:
                    connection.timeout = 14400
                    cursor = connection.cursor()
                    cursor.execute("SELECT @@SPID")
                    row = cursor.fetchone()
                    worker_state["spid"] = int(row[0]) if row else None
                    ready.set()
                    cursor.execute(sql, backup_path)
                    self._consume_all_results(cursor)
            except Exception as exc:  # noqa: BLE001
                worker_state["error"] = exc
                ready.set()
            finally:
                finished.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        ready.wait(timeout=20)
        spid = worker_state.get("spid")
        monitor_failed = False
        while not finished.wait(timeout=2):
            percent = None
            if spid and not monitor_failed:
                try:
                    percent = self._backup_percent(odbc_string, spid)
                except Exception:  # noqa: BLE001 - Το VIEW SERVER STATE μπορεί να μην επιτρέπεται.
                    monitor_failed = True
                    logger.info("Live SQL backup percentage is unavailable.")
            message = (
                f"SQL Server backup progress: {percent:.1f}%"
                if percent is not None
                else "SQL Server backup is running..."
            )
            self._emit(progress_callback, "backup", message, percent)
        thread.join()
        if worker_state.get("error"):
            raise worker_state["error"]

    @staticmethod
    def _backup_percent(odbc_string: str, spid: int) -> float | None:
        with pyodbc.connect(odbc_string, timeout=10, autocommit=True) as connection:
            connection.timeout = 10
            cursor = connection.cursor()
            cursor.execute(
                "SELECT percent_complete FROM sys.dm_exec_requests WHERE session_id = ?",
                spid,
            )
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] is not None else None

    def _verify_backup(self, connection_string: str, backup_path: str) -> None:
        with pyodbc.connect(
            self._to_odbc_connection_string(connection_string),
            timeout=60,
            autocommit=True,
        ) as connection:
            connection.timeout = 7200
            cursor = connection.cursor()
            cursor.execute(
                "DECLARE @backup_path nvarchar(4000) = ?; "
                "RESTORE VERIFYONLY FROM DISK = @backup_path WITH CHECKSUM;",
                backup_path,
            )
            self._consume_all_results(cursor)

    def _cloud_retention(
        self, settings: dict[str, Any], database_token: str
    ) -> list[str]:
        if settings["retention_mode"] != "keep_last":
            return []
        return self.cloud_adapter.enforce_keep_last(
            settings["cloud_remote"], database_token, settings["retention_count"]
        )

    @staticmethod
    def _local_keep_last(
        folder: str, database_token: str, keep_count: int
    ) -> list[str]:
        pattern = re.compile(
            rf"^{re.escape(database_token)}_\d{{8}}_\d{{6}}_\d{{3}}\.bak$",
            re.IGNORECASE,
        )
        files = []
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_file() and pattern.fullmatch(entry.name):
                    files.append(entry)
        files.sort(key=lambda entry: (entry.stat().st_mtime, entry.name), reverse=True)
        deleted: list[str] = []
        for entry in files[keep_count:]:
            os.remove(entry.path)
            deleted.append(entry.name)
        return deleted

    @staticmethod
    def _sha256(file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _consume_all_results(cursor) -> None:
        while True:
            if cursor.description:
                while cursor.fetchmany(100):
                    pass
            if not cursor.nextset():
                break

    def _acquire_database(self, database_name: str) -> bool:
        key = database_name.casefold()
        with self._active_lock:
            if key in self._active_databases:
                return False
            self._active_databases.add(key)
            return True

    def _release_database(self, database_name: str) -> None:
        with self._active_lock:
            self._active_databases.discard(database_name.casefold())

    @staticmethod
    def _emit(
        callback: Callable[[dict[str, Any]], None] | None,
        stage: str,
        message: str,
        percent: float | None,
    ) -> None:
        if not callback:
            return
        payload: dict[str, Any] = {"stage": stage, "message": str(message)[:1000]}
        if percent is not None:
            payload["percent"] = max(0.0, min(float(percent), 100.0))
        callback(payload)

    @staticmethod
    def _safe_database_token(database_name: str) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]+", "_", str(database_name)).strip("._-")
        if not token:
            raise BackupValidationError(
                "Database name cannot be converted to a safe file name."
            )
        return token[:120]

    @staticmethod
    def _parse_connection_string(connection_string: str) -> dict[str, str]:
        key_map = {
            "server": "server",
            "data source": "server",
            "database": "database",
            "initial catalog": "database",
            "user id": "user_id",
            "uid": "user_id",
            "password": "password",
            "pwd": "password",
        }
        result: dict[str, str] = {}
        for item in str(connection_string or "").split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            mapped = key_map.get(re.sub(r"\s+", " ", key.strip().lower()))
            if mapped:
                result[mapped] = value.strip()
        return result

    @classmethod
    def _to_odbc_connection_string(cls, connection_string: str) -> str:
        parts = cls._parse_connection_string(connection_string)
        if not parts.get("server") or not parts.get("database"):
            raise BackupValidationError(
                "Missing SQL Server or database in connection string."
            )
        driver = cls._get_available_sql_driver()
        return (
            ";".join(
                [
                    f"DRIVER={{{driver}}}",
                    f"SERVER={parts['server']}",
                    f"DATABASE={parts['database']}",
                    f"UID={parts.get('user_id', '')}",
                    f"PWD={parts.get('password', '')}",
                    "Encrypt=no",
                    "TrustServerCertificate=yes",
                ]
            )
            + ";"
        )

    @staticmethod
    def _get_available_sql_driver() -> str:
        installed = pyodbc.drivers()
        for driver in (
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ):
            if driver in installed:
                return driver
        raise RuntimeError("No compatible SQL Server ODBC driver was found.")

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return "[" + value.replace("]", "]]") + "]"

    @classmethod
    def _sanitize_error(cls, error: str, connection_string: str) -> str:
        safe = str(error or "Database backup failed.")
        if connection_string:
            safe = safe.replace(connection_string, "[REDACTED CONNECTION]")
        parsed = cls._parse_connection_string(connection_string)
        for key in ("password", "user_id"):
            secret = parsed.get(key, "")
            if secret:
                safe = safe.replace(secret, "***")
        return safe[:4000]


class BackupCoordinator:
    """Συνδέει backup engine, schedules, history και AppSettings BOConnections."""

    OPERATIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "run",
            "list",
            "save_schedule",
            "delete_schedule",
            "run_schedule",
            "retry_pending",
            "list_cloud_remotes",
        }
    )

    def __init__(
        self,
        appsettings_reader,
        state_file: Path,
        rclone_executable: str,
        rclone_config_file: Path,
    ) -> None:
        self.appsettings_reader = appsettings_reader
        self.store = BackupStateStore(state_file)
        self.cloud_adapter = RcloneCloudAdapter(rclone_executable, rclone_config_file)
        self.backup_service = SqlServerBackupService(self.cloud_adapter)

    def execute(
        self,
        operation: str,
        bo_connection_id: int,
        parameters: dict[str, Any] | None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Εκτελεί μόνο allowlisted backup operation."""

        clean_operation = str(operation or "").strip().lower()
        values = parameters if isinstance(parameters, dict) else {}
        if clean_operation not in self.OPERATIONS:
            return self._failure(clean_operation, "Unsupported backup operation.")
        try:
            if clean_operation == "list":
                return {
                    "success": True,
                    "operation": clean_operation,
                    **self.store.snapshot(),
                }
            if clean_operation == "list_cloud_remotes":
                return {
                    "success": True,
                    "operation": clean_operation,
                    "cloud_remotes": self.cloud_adapter.list_remotes(),
                }
            if clean_operation == "save_schedule":
                schedule = self.store.save_schedule(values.get("schedule", {}))
                return {
                    "success": True,
                    "operation": clean_operation,
                    "message": "Backup schedule saved successfully.",
                    "schedule": schedule,
                }
            if clean_operation == "delete_schedule":
                deleted = self.store.delete_schedule(
                    str(values.get("schedule_id") or "")
                )
                if not deleted:
                    raise BackupValidationError("Backup schedule was not found.")
                return {
                    "success": True,
                    "operation": clean_operation,
                    "message": "Backup schedule deleted successfully.",
                }
            if clean_operation == "retry_pending":
                return self.retry_pending(
                    progress_callback=progress_callback, force=True
                )
            if clean_operation == "run_schedule":
                schedule_id = str(values.get("schedule_id") or "")
                schedule = self.store.get_schedule(schedule_id)
                if not schedule:
                    raise BackupValidationError("Backup schedule was not found.")
                return self._run_schedule(schedule, progress_callback)
            settings = BackupSettingsValidator.backup_settings(
                values.get("settings", {})
            )
            return self._run_backup(
                bo_connection_id=bo_connection_id,
                settings=settings,
                source="manual",
                schedule_id="",
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.exception(
                "Backup coordinator operation failed. operation=%s", clean_operation
            )
            return self._failure(clean_operation, str(exc)[:4000])

    def run_due_schedules(self) -> None:
        """Εκτελεί σειριακά schedules που δεσμεύτηκαν ως due."""

        for schedule in self.store.claim_due():
            result = self._run_schedule(schedule, progress_callback=None)
            logger.info(
                "Scheduled backup finished. schedule_id=%s success=%s status=%s",
                schedule.get("schedule_id"),
                result.get("success"),
                result.get("status"),
            )

    def retry_pending(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Επαναλαμβάνει pending cloud uploads χωρίς να δημιουργεί νέο SQL backup."""

        entries = (
            self.store.snapshot()["history"]
            if force
            else self.store.retryable_uploads()
        )
        entries = [entry for entry in entries if entry.get("status") == "upload_failed"]
        completed = 0
        failed = 0
        for entry in entries:
            result = self.backup_service.retry_upload(entry, progress_callback)
            retry_count = int(entry.get("retry_count", 0)) + 1
            changes = {
                **result,
                "retry_count": retry_count,
                "finished_at": datetime.now().astimezone().isoformat(),
                "next_retry_at": (
                    None
                    if result.get("success")
                    else (
                        datetime.now().astimezone()
                        + timedelta(minutes=min(15 * (2 ** (retry_count - 1)), 360))
                    ).isoformat()
                ),
            }
            self.store.update_history(str(entry.get("history_id")), changes)
            if result.get("success"):
                completed += 1
            else:
                failed += 1
        return {
            "success": failed == 0,
            "operation": "retry_pending",
            "status": "completed" if failed == 0 else "upload_failed",
            "message": f"Cloud upload retries completed: {completed} succeeded, {failed} failed.",
            "retried": completed + failed,
            "completed": completed,
            "failed": failed,
        }

    def _run_schedule(
        self,
        schedule: dict[str, Any],
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        result = self._run_backup(
            bo_connection_id=int(schedule["bo_connection_id"]),
            settings=BackupSettingsValidator.backup_settings(schedule["settings"]),
            source="schedule",
            schedule_id=str(schedule["schedule_id"]),
            progress_callback=progress_callback,
        )
        self.store.record_schedule_result(
            str(schedule["schedule_id"]),
            str(result.get("status") or "failed"),
            str(result.get("message") or result.get("error") or ""),
        )
        return result

    def _run_backup(
        self,
        bo_connection_id: int,
        settings: dict[str, Any],
        source: str,
        schedule_id: str,
        progress_callback: Callable[[dict[str, Any]], None] | None,
    ) -> dict[str, Any]:
        connection_string = self._database_connection(bo_connection_id)
        started_at = datetime.now().astimezone().isoformat()
        result = self.backup_service.execute(
            connection_string, settings, progress_callback=progress_callback
        )
        history = {
            **result,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(),
            "source": source,
            "schedule_id": schedule_id or None,
            "bo_connection_id": bo_connection_id,
            "settings": BackupSettingsValidator.public_settings(settings),
            "retry_count": 0,
            "next_retry_at": (
                (datetime.now().astimezone() + timedelta(minutes=15)).isoformat()
                if result.get("status") == "upload_failed"
                else None
            ),
        }
        saved = self.store.append_history(history)
        return {**result, "operation": "run", "history_id": saved["history_id"]}

    def _database_connection(self, bo_connection_id: int) -> str:
        if type(bo_connection_id) is not int or not 1 <= bo_connection_id <= 2147483647:
            raise BackupValidationError("Invalid bo_connection_id.")
        data = self.appsettings_reader.read_appsettings_production()
        for connection in data.get("bo_connections") or []:
            try:
                connection_id = int(connection.get("ID"))
            except (TypeError, ValueError):
                continue
            if connection_id != bo_connection_id:
                continue
            value = str(connection.get("DatabaseConnection") or "")
            if value:
                return value
        raise RuntimeError(f"BOConnection ID {bo_connection_id} was not found.")

    @staticmethod
    def _failure(operation: str, error: str) -> dict[str, Any]:
        return {
            "success": False,
            "operation": operation,
            "status": "failed",
            "message": "Backup operation failed.",
            "error": error,
        }


class BackupScheduler:
    """Ελέγχει περιοδικά τα client-local schedules χωρίς εξωτερική βιβλιοθήκη."""

    def __init__(
        self, coordinator: BackupCoordinator, interval_seconds: int = 30
    ) -> None:
        self.coordinator = coordinator
        self.interval_seconds = max(10, min(int(interval_seconds), 300))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Ξεκινά ένα μόνο daemon scheduler thread."""

        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="MoonHardBackupScheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("Ο backup scheduler ξεκίνησε.")

    def stop(self) -> None:
        """Ζητά ασφαλή τερματισμό του scheduler."""

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Εκτελεί due schedules και αυτόματα retries με απομονωμένα errors."""

        while not self._stop_event.is_set():
            try:
                self.coordinator.run_due_schedules()
                self.coordinator.retry_pending(force=False)
            except Exception:
                logger.exception("Απρόσμενο σφάλμα backup scheduler.")
            self._stop_event.wait(self.interval_seconds)
