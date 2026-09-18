"""Ανάγνωση ασφαλών AppSettings από CLI με το υπάρχον πρωτόκολλο του server."""

import argparse
import asyncio
import json
import logging
import sys

import websockets

from app.appsettings_presenter import AppSettingsPresenter
from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig

logger = logging.getLogger(__name__)


class AppSettingsCLI:
    """Προσφέρει τις ίδιες προστατευμένες πληροφορίες με την καρτέλα του Dashboard."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        """Ορίζει επιλογή Client, BOConnection και συνοπτική λίστα συνδέσεων."""
        parser = argparse.ArgumentParser(description="Προβολή ασφαλών AppSettings από τον MoonHard Server.")
        parser.add_argument("--client", required=True, help="Κωδικός Client.")
        parser.add_argument("--bo-connection", type=int, help="Περιορισμός σε ένα BOConnection ID.")
        parser.add_argument("--list-connections", action="store_true", help="Μόνο ID και όνομα βάσης.")
        return parser

    async def request(self, config, client_code: str) -> dict:
        """Ανακτά το τελευταίο αποθηκευμένο αποτέλεσμα, όχι το αρχείο στον Client."""
        if not config.dashboard_token:
            raise ValueError("Δεν έχει οριστεί DASHBOARD_TOKEN.")
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15, close_timeout=5) as ws:
            await ws.send(json.dumps({"type": "authenticate", "token": config.dashboard_token}))
            async def authenticate():
                """Αγνοεί αρχικές ενημερώσεις μέχρι την επιβεβαίωση αυθεντικοποίησης."""
                while True:
                    result = json.loads(await ws.recv())
                    if result.get("type") == "dashboard_connected":
                        return
                    if result.get("type") == "error":
                        raise ValueError("Απέτυχε η αυθεντικοποίηση.")
            await asyncio.wait_for(authenticate(), 15)
            await ws.send(json.dumps({"type": "get_client_appsettings", "client_code": client_code}))
            async def receive():
                """Απορρίπτει ενημερώσεις και αποτελέσματα άλλου Client."""
                while True:
                    result = json.loads(await ws.recv())
                    if result.get("type") == "client_appsettings_result" and result.get("client_code") == client_code:
                        return result
            return await asyncio.wait_for(receive(), 30)

    @staticmethod
    def render(payload: dict, args) -> dict:
        """Εφαρμόζει απόκρυψη πριν από οποιαδήποτε εκτύπωση ή αντιγραφή."""
        if not payload.get("success"):
            raise ValueError("Αποτυχία ανάκτησης AppSettings.")
        data = AppSettingsPresenter.safe_data(payload.get("appsettings") or {})
        if args.bo_connection is not None:
            data["bo_connections"] = [item for item in data["bo_connections"]
                                      if str(item.get("ID")) == str(args.bo_connection)]
            if not data["bo_connections"]:
                raise ValueError("Δεν βρέθηκε το ζητούμενο BOConnection ID.")
            data["selected_bo_connection_id"] = args.bo_connection
        if args.list_connections:
            return {"bo_connections": [{"ID": item.get("ID"), "DatabaseName": item.get("DatabaseName") or
                    AppSettingsPresenter.connection_parts(item.get("DatabaseConnection", "")).get("database")}
                    for item in data["bo_connections"]]}
        return data

    def run(self, argv=None) -> int:
        """Εκτυπώνει UTF-8 JSON και καταγράφει μόνο στοιχεία της ενέργειας."""
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        args = self.parser().parse_args(argv)
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(sys.stderr)
        try:
            payload = asyncio.run(self.request(config, args.client))
            print(json.dumps(self.render(payload, args), ensure_ascii=False, indent=2))
            logger.info("Ανάκτηση CLI AppSettings ολοκληρώθηκε.")
            return 0
        except Exception as exc:
            logger.error("Αποτυχία CLI AppSettings. exception_type=%s", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else "Αποτυχία σύνδεσης ή λήξη αναμονής."
            print(json.dumps({"success": False, "message": message}, ensure_ascii=False), file=sys.stderr)
            return 1


def main(argv=None) -> int:
    """Κοινό σημείο εισόδου για source και console EXE."""
    return AppSettingsCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
