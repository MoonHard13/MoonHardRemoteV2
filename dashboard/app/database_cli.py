import argparse
import asyncio
import json
import logging
import sys
import uuid
from typing import ClassVar

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig

logger = logging.getLogger(__name__)


class DatabaseCLI:
    """Εκτελεί τις ίδιες ελεγχόμενες database actions από CMD."""

    ACTIONS = (
        "test-connection",
        "sales-trans-info",
        "mydata-info",
        "clean-mydata",
        "history",
        "shrink",
        "rebuild",
    )
    MUTATING_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {"clean-mydata", "history", "shrink", "rebuild"}
    )
    WAIT_SECONDS: ClassVar[dict[str, int]] = {
        "test-connection": 60,
        "sales-trans-info": 90,
        "mydata-info": 90,
        "clean-mydata": 645,
        "history": 1845,
        "shrink": 3645,
        "rebuild": 7245,
    }

    @classmethod
    def parser(cls) -> argparse.ArgumentParser:
        """Ορίζει τις διαθέσιμες λειτουργίες και τα απαιτούμενα arguments."""

        parser = argparse.ArgumentParser(
            description="MoonHard Remote database maintenance through an online client."
        )
        parser.add_argument("action", choices=cls.ACTIONS)
        parser.add_argument("--client", required=True, help="Remote client code.")
        parser.add_argument("--bo-connection", type=int, default=1)
        parser.add_argument(
            "--from-date", default="", help="YYYYMMDD for clean-mydata."
        )
        parser.add_argument("--to-date", default="", help="YYYYMMDD for clean-mydata.")
        parser.add_argument("--date", default="", help="YYYYMMDD for history.")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required confirmation for actions that change database data.",
        )
        return parser

    @classmethod
    def build_payload(cls, args) -> dict:
        """Μετατρέπει τα CLI arguments στο αυστηρό WebSocket payload."""

        if args.action in cls.MUTATING_ACTIONS and not args.yes:
            raise ValueError(
                "This action changes the database. Run it again with --yes after verifying the target and backup."
            )

        parameters: dict[str, str] = {}
        if args.action == "clean-mydata":
            if not args.from_date or not args.to_date:
                raise ValueError("clean-mydata requires --from-date and --to-date.")
            parameters = {"start_date": args.from_date, "end_date": args.to_date}
        elif args.action == "history":
            if not args.date:
                raise ValueError("history requires --date.")
            parameters = {"history_date": args.date}

        return {
            "type": "database_action",
            "request_id": str(uuid.uuid4()),
            "client_code": args.client,
            "bo_connection_id": args.bo_connection,
            "action": args.action.replace("-", "_"),
            "parameters": parameters,
        }

    async def request(
        self, config: DashboardConfig, payload: dict, wait_seconds: int
    ) -> dict:
        """Αυθεντικοποιείται, στέλνει την ενέργεια και περιμένει το συσχετισμένο αποτέλεσμα."""

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
            logger.info(
                "Database CLI request sent. action=%s client_code=%s",
                payload["action"],
                payload["client_code"],
            )

            async def receive() -> dict:
                """Αγνοεί άσχετα status messages μέχρι να φτάσει η σωστή απάντηση."""

                async for message in websocket:
                    result = json.loads(message)
                    if (
                        result.get("type") == "database_action_result"
                        and result.get("request_id") == payload["request_id"]
                        and result.get("client_code") == payload["client_code"]
                        and result.get("bo_connection_id")
                        == payload["bo_connection_id"]
                        and result.get("action") == payload["action"]
                    ):
                        return result
                raise ValueError(
                    "The connection closed before a database result was received."
                )

            return await asyncio.wait_for(receive(), timeout=wait_seconds)

    def run(self, argv=None) -> int:
        """Εκτελεί το CLI και επιστρέφει κατάλληλο process exit code."""

        parser = self.parser()
        args = parser.parse_args(argv)
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(sys.stderr)

        try:
            payload = self.build_payload(args)
            result = asyncio.run(
                self.request(config, payload, self.WAIT_SECONDS[args.action])
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("success") else 1
        except Exception as exc:  # noqa: BLE001 - Το CLI μετατρέπει κάθε αστοχία μεταφοράς σε ασφαλές exit code.
            logger.error("Database CLI failed. exception_type=%s", type(exc).__name__)
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "Connection failed or the request timed out."
            )
            print(
                json.dumps({"success": False, "error": message}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1


def main(argv=None) -> int:
    """Σημείο εισόδου για το dashboard executable και python -m."""

    return DatabaseCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
