import argparse
import asyncio
import json
import logging
from pathlib import Path

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig
from app.provider_diagnostic.context import CustomerContextAdapter
from app.provider_diagnostic.sections import SECTIONS
from app.provider_diagnostic.security import SECRET_REDACTOR


logger = logging.getLogger(__name__)


class ProviderDiagnosticCLI:
    """Ανάγνωση υπάρχοντος customer context και χειρισμός exported diagnostics από CMD."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="MoonHard Provider Diagnostic Center · Phase 1")
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument("--client", help="Υπάρχων κωδικός client για ανάγνωση context.")
        actions.add_argument("--sections", action="store_true", help="Εμφάνιση ενοτήτων και φάσεων.")
        actions.add_argument("--diagnostics-file", type=Path, help="JSON που εξήχθη από το API Diagnostics GUI.")
        parser.add_argument("--bo-connection", type=int, default=1)
        parser.add_argument("--outcome", choices=("All", "Success", "Errors"), default="All")
        parser.add_argument("--endpoint", default="")
        parser.add_argument("--status", default="")
        parser.add_argument("--output", type=Path, help="Αποθήκευση JSON· διαφορετικά εκτύπωση για copy/pipe.")
        return parser

    @staticmethod
    def parse_connection(value: str) -> dict:
        result = {}
        for item in value.split(";"):
            if "=" not in item:
                continue
            key, text = item.split("=", 1)
            name = {"server": "server", "data source": "server",
                    "database": "database", "initial catalog": "database"}.get(key.strip().lower())
            if name:
                result[name] = text.strip()
        return result

    async def context(self, config: DashboardConfig, client_code: str, bo_id: int) -> dict:
        if not config.dashboard_token or bo_id < 1 or not client_code or len(client_code) > 128:
            raise ValueError("Ελέγξτε DASHBOARD_TOKEN, client code και BOConnection ID.")
        SECRET_REDACTOR.register(config.dashboard_token)
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15,
                                      close_timeout=5, max_size=8 * 1024 * 1024) as websocket:
            await websocket.send(json.dumps({"type": "authenticate", "token": config.dashboard_token}))
            reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
            if reply.get("type") != "dashboard_connected":
                raise ValueError("Απέτυχε η αυθεντικοποίηση του Dashboard.")
            await websocket.send(json.dumps({"type": "get_client_appsettings", "client_code": client_code}))

            async def receive() -> dict:
                client = None
                settings = None
                async for raw in websocket:
                    reply = json.loads(raw)
                    if reply.get("type") == "clients_list":
                        client = next((row for row in reply.get("clients", [])
                                       if row.get("client_code") == client_code), None)
                        if client is None:
                            raise ValueError("Ο client δεν βρέθηκε στην υπάρχουσα λίστα.")
                    if reply.get("type") == "client_appsettings_result" and reply.get("client_code") == client_code:
                        if not reply.get("success"):
                            raise ValueError("Δεν ήταν δυνατή η ανάκτηση του customer context.")
                        settings = reply.get("appsettings") or {}
                    if client is not None and settings is not None:
                        bo = next((row for row in settings.get("bo_connections", [])
                                   if str(row.get("ID")) == str(bo_id)), {})
                        return CustomerContextAdapter(lambda: client, lambda: bo,
                            lambda: bo_id, self.parse_connection).snapshot().to_dict()
                raise ValueError("Η σύνδεση έκλεισε πριν ολοκληρωθεί η ανάγνωση.")

            return await asyncio.wait_for(receive(), timeout=30)

    @staticmethod
    def diagnostics(args) -> list[dict]:
        if args.diagnostics_file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Το αρχείο διαγνωστικών υπερβαίνει το επιτρεπτό μέγεθος.")
        rows = json.loads(args.diagnostics_file.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Μη έγκυρη δομή αρχείου διαγνωστικών.")
        return [row for row in rows
                if (args.outcome == "All" or row.get("Result") == ("Success" if args.outcome == "Success" else "Failure"))
                and args.endpoint.lower() in str(row.get("Endpoint", "")).lower()
                and (not args.status or str(row.get("HTTP Status", "")) == args.status)]

    def run(self, argv=None) -> int:
        args = self.parser().parse_args(argv)
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        try:
            if args.sections:
                result = {"phase": 1, "sections": SECTIONS}
            elif args.diagnostics_file:
                result = {"scope": "Το επιλεγμένο export· δεν διαβάζεται η RAM άλλου Dashboard process.",
                          "diagnostics": self.diagnostics(args)}
            else:
                result = asyncio.run(self.context(config, args.client, args.bo_connection))
            text = json.dumps(SECRET_REDACTOR.redact_object(result), ensure_ascii=False, indent=2)
            if args.output:
                args.output.write_text(text + "\n", encoding="utf-8")
            else:
                print(text)
            logger.info("CLI Provider Diagnostic Center ολοκληρώθηκε.")
            return 0
        except KeyboardInterrupt:
            logger.info("Ακύρωση CLI Provider Diagnostic Center.")
            return 130
        except Exception:
            print(json.dumps({"success": False, "error": "Απέτυχε η ανάγνωση ή αποθήκευση. Ελέγξτε σύνδεση, ρυθμίσεις και δικαιώματα αρχείου."}, ensure_ascii=False))
            logger.warning("Αποτυχία CLI Provider Diagnostic Center.")
            return 1


def main(argv=None) -> int:
    return ProviderDiagnosticCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
