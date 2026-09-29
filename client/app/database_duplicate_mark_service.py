from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from app.database_maintenance_service import DatabaseMaintenanceService


class DuplicateMarkDatabaseMaintenanceService(DatabaseMaintenanceService):
    """Επεκτείνει τις database actions με το cleanup διπλών ΜΑΡΚ."""

    ACTION = "delete_duplicate_mark"
    ACTIONS = frozenset(set(DatabaseMaintenanceService.ACTIONS) | {ACTION})
    SQL_DIR = Path(__file__).resolve().parent / "sql"
    SUCCESS_SCRIPT = "!Delete_Duplicate_Success_Mark.sql"
    MARK_SCRIPT = "!Delete_Duplicate_MArK.sql"

    def _execute_action(
        self,
        cursor,
        action: str,
        parameters: dict[str, Any],
        database_name: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Εκτελεί τα δύο scripts σειριακά, με best-effort μόνο στο πρώτο."""

        if action != self.ACTION:
            return super()._execute_action(
                cursor=cursor,
                action=action,
                parameters=parameters,
                database_name=database_name,
                progress_callback=progress_callback,
            )

        self._emit_progress(
            progress_callback,
            stage="success",
            percent=10,
            message="Step 1/2: running Duplicate Success MARK cleanup...",
        )
        success_step = self._run_optional_success_step(cursor)
        self._emit_progress(
            progress_callback,
            stage="success" if success_step["success"] else "success_warning",
            percent=45,
            message=(
                "Step 1/2: Duplicate Success MARK cleanup completed."
                if success_step["success"]
                else "Step 1/2: Success cleanup skipped with warning. Continuing..."
            ),
        )

        self._emit_progress(
            progress_callback,
            stage="mark",
            percent=55,
            message="Step 2/2: running Duplicate MARK cleanup...",
        )
        mark_step = self._run_required_mark_step(cursor)

        if not mark_step["success"]:
            self._emit_progress(
                progress_callback,
                stage="mark_failed",
                percent=100,
                message="Step 2/2: Duplicate MARK cleanup failed.",
            )
            return {
                "success": False,
                "error": mark_step.get("error") or "Duplicate MARK cleanup failed.",
                "message": "Duplicate MARK cleanup failed.",
                "success_step": success_step,
                "mark_step": mark_step,
            }

        self._emit_progress(
            progress_callback,
            stage="completed",
            percent=100,
            message="Duplicate MARK cleanup completed.",
        )
        return {
            "message": (
                "Duplicate MARK cleanup completed successfully."
                if success_step["success"]
                else "Duplicate MARK cleanup completed with a warning in optional Step 1."
            ),
            "success_step": success_step,
            "mark_step": mark_step,
        }

    def _run_optional_success_step(self, cursor) -> dict[str, Any]:
        """Το πρώτο script μπορεί να αποτύχει χωρίς να σταματήσει το κύριο cleanup."""

        try:
            script = self._read_script(self.SUCCESS_SCRIPT)
            deleted_rows = self._execute_script(cursor, script)
            return {
                "success": True,
                "message": "Duplicate Success MARK cleanup completed.",
                "deleted_rows": deleted_rows,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - SQL Server drivers έχουν διαφορετικά exceptions.
            return {
                "success": False,
                "message": "Optional Success cleanup was not applied; main cleanup continued.",
                "deleted_rows": None,
                "error": str(exc)[:1200],
            }

    def _run_required_mark_step(self, cursor) -> dict[str, Any]:
        """Το δεύτερο script είναι το κύριο βήμα και καθορίζει το τελικό αποτέλεσμα."""

        try:
            script = self._read_script(self.MARK_SCRIPT)
            deleted_rows = self._execute_script(cursor, script)
            return {
                "success": True,
                "message": "Duplicate MARK cleanup completed.",
                "deleted_rows": deleted_rows,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "message": "Duplicate MARK cleanup failed.",
                "deleted_rows": None,
                "error": str(exc)[:1200],
            }

    def _read_script(self, filename: str) -> str:
        """Διαβάζει μόνο allowlisted SQL resource από τον φάκελο του client package."""

        if filename not in {self.SUCCESS_SCRIPT, self.MARK_SCRIPT}:
            raise ValueError("Unsupported duplicate MARK SQL resource.")

        path = self.SQL_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required SQL resource was not found: {filename}")
        return path.read_text(encoding="utf-8-sig")

    def _execute_script(self, cursor, script: str) -> int | None:
        """Εκτελεί SSMS-style script χωρίζοντας αποκλειστικά standalone GO batches."""

        batches = [
            batch.strip()
            for batch in re.split(r"(?im)^\s*GO\s*;?\s*$", script)
            if batch.strip()
        ]
        if not batches:
            raise ValueError("SQL resource is empty.")

        deleted_rows = 0
        rowcount_known = False
        for batch in batches:
            cursor.execute(batch)
            rowcount = getattr(cursor, "rowcount", -1)
            if type(rowcount) is int and rowcount >= 0:
                deleted_rows += rowcount
                rowcount_known = True
            self._consume_all_results(cursor)

        return deleted_rows if rowcount_known else None

    @staticmethod
    def _emit_progress(
        callback: Callable[[dict[str, Any]], None] | None,
        stage: str,
        percent: int,
        message: str,
    ) -> None:
        if callback:
            callback(
                {
                    "stage": stage,
                    "percent": percent,
                    "message": message,
                }
            )
