import argparse
import asyncio
import json
import logging
import sys
import uuid
from typing import Any, ClassVar

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig

logger = logging.getLogger(__name__)


class BackupCLI:
    """Παρέχει πλήρη CLI πρόσβαση σε manual backups και schedules."""

    OPERATIONS: ClassVar[tuple[str, ...]] = (
        "run",
        "list",
        "save-schedule",
        "delete-schedule",
        "run-schedule",
        "retry-pending",
        "list-cloud-remotes",
    )
    MUTATING = frozenset(
        {"run", "save-schedule", "delete-schedule", "run-schedule", "retry-pending"}
    )

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="MoonHard Remote SQL Server backup and schedule management."
        )
        parser.add_argument("operation", choices=cls.OPERATIONS)
        parser.add_argument("--client", required=True, help="Remote client code.")
        parser.add_argument("--bo-connection", type=int, default=1)
        parser.add_argument("--schedule-id", default="")
        parser.add_argument("--name", default="")
        parser.add_argument(
            "--frequency", choices=("daily", "weekly", "monthly"), default="daily"
        )
        parser.add_argument("--time", default="02:00", help="Local client time HH:MM.")
        parser.add_argument(
            "--weekday", type=int, default=0, help="Monday=0, Sunday=6."
        )
        parser.add_argument("--day-of-month", type=int, default=1)
        parser.add_argument("--disabled", action="store_true")
        parser.add_argument(
            "--destination-type", choices=("local", "unc", "cloud"), default="local"
        )
        parser.add_argument("--destination-path", default=r"C:\MoonHardBackups")
        parser.add_argument(
            "--staging-path",
            default=r"C:\ProgramData\MoonHardRemoteV2\backups\staging",
        )
        parser.add_argument("--cloud-remote", default="")
        parser.add_argument(
            "--retention-mode",
            choices=("replace", "keep-all", "keep-last"),
            default="keep-last",
        )
        parser.add_argument("--keep", type=int, default=7)
        parser.add_argument("--no-compression", action="store_true")
        parser.add_argument("--no-copy-only", action="store_true")
        parser.add_argument("--yes", action="store_true")
        return parser

    @classmethod
    def build_payload(cls, args) -> dict[str, Any]:
        """Μετατρέπει arguments σε αυστηρό backup protocol payload."""

        if args.operation in cls.MUTATING and not args.yes:
            raise ValueError(
                "This operation changes backup files or schedules. Run it again with --yes."
            )
        operation = args.operation.replace("-", "_")
        parameters: dict[str, Any] = {}
        if operation == "run":
            parameters = {"settings": cls._settings(args)}
        elif operation == "save_schedule":
            if not args.name:
                raise ValueError("save-schedule requires --name.")
            parameters = {
                "schedule": {
                    "schedule_id": args.schedule_id,
                    "name": args.name,
                    "bo_connection_id": args.bo_connection,
                    "frequency": args.frequency,
                    "time": args.time,
                    "weekday": args.weekday,
                    "day_of_month": args.day_of_month,
                    "enabled": not args.disabled,
                    "settings": cls._settings(args),
                }
            }
        elif operation in {"delete_schedule", "run_schedule"}:
            if not args.schedule_id:
                raise ValueError(f"{args.operation} requires --schedule-id.")
            parameters = {"schedule_id": args.schedule_id}
        return {
            "type": "backup_request",
            "request_id": str(uuid.uuid4()),
            "client_code": args.client,
            "bo_connection_id": args.bo_connection,
            "operation": operation,
            "parameters": parameters,
        }

    @staticmethod
    def _settings(args) -> dict[str, Any]:
        if not 1 <= args.keep <= 365:
            raise ValueError("--keep must be between 1 and 365.")
        return {
            "destination_type": args.destination_type,
            "destination_path": args.destination_path,
            "staging_path": args.staging_path,
            "cloud_remote": args.cloud_remote,
            "retention_mode": args.retention_mode.replace("-", "_"),
            "retention_count": args.keep,
            "compression": not args.no_compression,
            "copy_only": not args.no_copy_only,
        }

    async def request(self, config: DashboardConfig, payload: dict[str, Any]) -> dict:
        """Αυθεντικοποιείται και περιμένει το correlated backup result."""

        if not config.dashboard_token:
            raise ValueError("DASHBOARD_TOKEN is not configured.")
        async with websockets.connect(
            config.dashboard_websocket_url,
            open_timeout=15,
            close_timeout=5,
        ) as websocket:
            await websocket.send(
                json.dumps({"type": "authenticate", "token": config.dashboard_token})
            )
            reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
            if reply.get("type") != "dashboard_connected":
                raise ValueError("Dashboard authentication failed.")
            await websocket.send(json.dumps(payload, ensure_ascii=False))
            async for message in websocket:
                result = json.loads(message)
                if (
                    result.get("request_id") != payload["request_id"]
                    or result.get("client_code") != payload["client_code"]
                ):
                    continue
                if result.get("type") == "backup_progress":
                    percent = result.get("percent")
                    prefix = f"[{float(percent):.1f}%] " if percent is not None else ""
                    print(
                        prefix + str(result.get("message") or ""),
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                if result.get("type") == "backup_result":
                    return result
            raise ValueError("Connection closed before the backup result was received.")

    def run(self, argv=None) -> int:
        parser = self.parser()
        args = parser.parse_args(argv)
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        try:
            payload = self.build_payload(args)
            result = asyncio.run(
                asyncio.wait_for(self.request(config, payload), timeout=14600)
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("success") else 1
        except Exception as exc:  # noqa: BLE001 - Το CLI μετατρέπει transport errors σε exit code.
            logger.error("Backup CLI failed. exception_type=%s", type(exc).__name__)
            message = (
                str(exc) if isinstance(exc, ValueError) else "Backup request failed."
            )
            print(json.dumps({"success": False, "error": message}), file=sys.stderr)
            return 1


def main(argv=None) -> int:
    return BackupCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
