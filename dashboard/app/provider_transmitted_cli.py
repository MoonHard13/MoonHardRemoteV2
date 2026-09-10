import argparse
import asyncio
import json
import logging
import sys
import uuid
import webbrowser

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig
from app.views.manage.provider_transmitted_window import DocumentLink


logger = logging.getLogger(__name__)


class TransmittedInvoicesCLI:
    """Αναζήτηση διαβιβασμένων από CMD με το ίδιο πρωτόκολλο του dashboard."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        """Ορίζει φίλτρα, σελιδοποίηση και χειρισμό του επιλεγμένου URL."""
        parser = argparse.ArgumentParser(description="Αναζήτηση διαβιβασμένων παραστατικών μέσω MoonHard Remote.")
        parser.add_argument("--client", required=True, help="Κωδικός απομακρυσμένου client.")
        parser.add_argument("--bo-connection", type=int, default=1)
        parser.add_argument("--from-date", default="", help="YYYYMMDD, YYYY-MM-DD ή ΗΗ/ΜΜ/ΕΕΕΕ.")
        parser.add_argument("--to-date", default="")
        parser.add_argument("--number", default="")
        parser.add_argument("--mark", default="")
        parser.add_argument("--document-type", default="", help="Τιμή note:OID ή mydata:κωδικός από --list-types.")
        parser.add_argument("--list-types", action="store_true")
        parser.add_argument("--before-oid", type=int)
        parser.add_argument("--limit", type=int, default=100)
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument("--open-response-oid", type=int, help="Ανοίγει το URL της εγγραφής της σελίδας στον browser.")
        actions.add_argument("--url-response-oid", type=int, help="Εκτυπώνει μόνο το URL για αντιγραφή, π.χ. με | clip.")
        return parser

    async def request(self, config: DashboardConfig, args) -> dict:
        """Αποστέλλει ένα αίτημα μετά την επιτυχή αυθεντικοποίηση και κλείνει τη σύνδεση."""
        if not config.dashboard_token:
            raise ValueError("Δεν έχει οριστεί DASHBOARD_TOKEN στις ρυθμίσεις του dashboard.")
        kind = "provider_transmitted_types" if args.list_types else "provider_transmitted_search"
        payload = {"type": kind, "request_id": str(uuid.uuid4()), "client_code": args.client,
                   "bo_connection_id": args.bo_connection, "start_date": args.from_date,
                   "end_date": args.to_date, "number": args.number, "mark": args.mark,
                   "document_type": args.document_type, "before_oid": args.before_oid, "limit": args.limit}
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15, close_timeout=5) as websocket:
            await websocket.send(json.dumps({"type": "authenticate", "token": config.dashboard_token}))
            reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
            if reply.get("type") != "dashboard_connected":
                raise ValueError("Απέτυχε η αυθεντικοποίηση του dashboard.")
            await websocket.send(json.dumps(payload, ensure_ascii=False))
            logger.info("CLI αίτημα διαβιβασμένων. type=%s", kind)
            async def receive() -> dict:
                """Αγνοεί ενημερώσεις κατάστασης και απαντήσεις άλλων αιτημάτων."""
                async for message in websocket:
                    result = json.loads(message)
                    if (result.get("request_id") == payload["request_id"]
                            and result.get("type") == f"{kind}_result"
                            and result.get("client_code") == args.client
                            and result.get("bo_connection_id") == args.bo_connection):
                        return result
                raise ValueError("Η σύνδεση έκλεισε πριν ληφθεί απάντηση.")
            return await asyncio.wait_for(receive(), timeout=85)

    def run(self, argv=None) -> int:
        """Εκτυπώνει JSON ή επιλεγμένο URL· επιστρέφει μη μηδενικό κωδικό σε αποτυχία."""
        parser = self.parser()
        args = parser.parse_args(argv)
        if args.list_types and (args.open_response_oid is not None or args.url_response_oid is not None):
            parser.error("Το --list-types δεν συνδυάζεται με ενέργειες URL.")
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(sys.stderr)
        try:
            result = asyncio.run(self.request(config, args))
            if not result.get("success"):
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
            selected_oid = args.open_response_oid if args.open_response_oid is not None else args.url_response_oid
            if selected_oid is not None:
                invoice = next((r for r in result.get("invoices", []) if r.get("ResponseOID") == selected_oid), None)
                if not invoice:
                    raise ValueError("Η εγγραφή δεν υπάρχει στην τρέχουσα σελίδα αποτελεσμάτων.")
                url = DocumentLink.validate(invoice.get("DocumentURL", ""))
                if args.url_response_oid is not None:
                    print(url)
                elif not webbrowser.open(url, new=2):
                    raise ValueError("Δεν άνοιξε ο browser. Χρησιμοποιήστε --url-response-oid.")
                logger.info("CLI ενέργεια URL ολοκληρώθηκε.")
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            logger.error("Αποτυχία CLI διαβιβασμένων. exception_type=%s", type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else "Αποτυχία σύνδεσης ή λήξη αναμονής απάντησης."
            print(json.dumps({"success": False, "error": message}, ensure_ascii=False), file=sys.stderr)
            return 1


def main(argv=None) -> int:
    """Σημείο εισόδου για python -m και για το εκτελέσιμο του dashboard."""
    return TransmittedInvoicesCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
