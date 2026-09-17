import argparse
import asyncio
import json
import logging
import webbrowser
from datetime import date
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig
from app.provider_diagnostic.context import CustomerContextAdapter
from app.provider_diagnostic.sections import SECTIONS
from app.provider_diagnostic.security import SECRET_REDACTOR
from app.provider_diagnostic.service import ProviderDiagnosticService
from app.provider_diagnostic.session import ProviderContextSession
from app.provider_diagnostic.errors import ProviderAPIError
from app.provider_diagnostic.models import ProviderEndpoint
from app.provider_diagnostic.documents import DocumentFields


logger = logging.getLogger(__name__)


class ProviderDiagnosticCLI:
    """Ανάγνωση υπάρχοντος customer context και χειρισμός exported diagnostics από CMD."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="MoonHard Provider Diagnostic Center · Phase 2")
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument("--client", help="Υπάρχων κωδικός client για ανάγνωση context.")
        actions.add_argument("--sections", action="store_true", help="Εμφάνιση ενοτήτων και φάσεων.")
        actions.add_argument("--diagnostics-file", type=Path, help="JSON που εξήχθη από το API Diagnostics GUI.")
        parser.add_argument("--bo-connection", type=int, default=1)
        parser.add_argument("--issuer-vat", default="", help="ΑΦΜ εταιρείας από τη βάση· απαιτείται όταν υπάρχουν πολλά.")
        operations = parser.add_mutually_exclusive_group()
        operations.add_argument("--probe", action="store_true", help="Ανάγνωση πρώτης σελίδας σημερινών παραστατικών.")
        operations.add_argument("--documents", action="store_true", help="Πλήρης ανάκτηση εξερχόμενων παραστατικών.")
        today = date.today().strftime("%Y%m%d")
        parser.add_argument("--date-from", default=today, help="Αρχή διαστήματος YYYYMMDD.")
        parser.add_argument("--date-to", default=today, help="Τέλος διαστήματος YYYYMMDD.")
        parser.add_argument("--series", default="")
        parser.add_argument("--number", default="")
        parser.add_argument("--invoice-type", default="", help="Ακριβής τύπος παραστατικού.")
        parser.add_argument("--mark", default="", help="Ακριβές MARK.")
        parser.add_argument("--open-document", type=int, help="Άνοιγμα URL ορατού παραστατικού με αρίθμηση από 1.")
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

    async def context(self, config: DashboardConfig, client_code: str, bo_id: int,
                      issuer_vat: str = "", probe: bool = False, documents: dict | None = None) -> dict:
        if not config.dashboard_token or bo_id < 1 or not client_code or len(client_code) > 128:
            raise ValueError("Ελέγξτε DASHBOARD_TOKEN, client code και BOConnection ID.")
        if urlsplit(config.dashboard_websocket_url).scheme != "wss":
            raise ValueError("Η ανάκτηση Provider στοιχείων απαιτεί κρυπτογραφημένη σύνδεση WSS.")
        session = ProviderContextSession()
        cancel = Event()
        chosen = issuer_vat.strip().upper()
        if chosen and not chosen.startswith("EL"):
            chosen = "EL" + chosen.removeprefix("GR")
        SECRET_REDACTOR.register(config.dashboard_token)
        try:
            async with websockets.connect(config.dashboard_websocket_url, open_timeout=15,
                                          close_timeout=5, max_size=8 * 1024 * 1024) as websocket:
                await websocket.send(json.dumps({"type": "authenticate", "token": config.dashboard_token}))
                reply = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
                if reply.get("type") != "dashboard_connected":
                    raise ValueError("Απέτυχε η αυθεντικοποίηση του Dashboard.")
                await websocket.send(json.dumps({"type": "get_client_appsettings", "client_code": client_code}))

                async def receive() -> dict:
                    client, settings, adapter = None, None, None
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
                        if client is not None and settings is not None and adapter is None:
                            bo = next((row for row in settings.get("bo_connections", [])
                                       if str(row.get("ID")) == str(bo_id)), {})
                            adapter = CustomerContextAdapter(lambda: client, lambda: bo,
                                lambda: bo_id, self.parse_connection)
                            await websocket.send(json.dumps(session.request(adapter.snapshot())))
                        if (adapter is not None and reply.get("type") == "provider_diagnostic_context_result"
                                and session.accept(reply, adapter.snapshot())):
                            context = adapter.snapshot()
                            result = {**context.to_dict(), "companies": session.companies,
                                      "issuer_vat": session.issuer_vat,
                                      "provider_base_url": session.provider_base_url,
                                      "documents_origin": ProviderEndpoint.documents_origin(session.provider_base_url) if session.provider_base_url else "",
                                      "provider_environment": ProviderEndpoint.environment(session.provider_base_url) if session.provider_base_url else "",
                                      "sql_verified": session.sql_verified,
                                      "invalid_afm_count": session.invalid_afm_count}
                            if reply.get("success") is not True or not session.context_valid:
                                return {**result, "success": False, "error": session.message}
                            if not probe and documents is None:
                                if chosen and chosen not in {row["issuer_vat"] for row in session.companies}:
                                    return {**result, "success": False, "error": "Το ΑΦΜ δεν υπάρχει στην επιλεγμένη βάση."}
                                selected = chosen or (session.companies[0]["issuer_vat"] if len(session.companies) == 1 else "")
                                return {**result, "success": True, "issuer_vat": selected}
                            if not session.issuer_vat:
                                selected = chosen or (session.companies[0]["issuer_vat"] if len(session.companies) == 1 else "")
                                if not selected:
                                    return {**result, "success": False, "error": "Υπάρχουν πολλά ΑΦΜ. Χρησιμοποιήστε --issuer-vat με ένα ΑΦΜ της λίστας."}
                                await websocket.send(json.dumps(session.request(context, selected)))
                            else:
                                service = ProviderDiagnosticService(adapter, session.resolve)
                                return result, service
                    raise ValueError("Η σύνδεση έκλεισε πριν ολοκληρωθεί η ανάγνωση.")

                ready = await asyncio.wait_for(receive(), timeout=180)
                if isinstance(ready, dict):
                    return ready
                result, service = ready
                try:
                    verified = service.snapshot()
                    if documents is not None:
                        dataset = await asyncio.wait_for(asyncio.to_thread(service.documents, verified,
                            documents["date_from"], documents["date_to"], cancel,
                            lambda value: logger.info("CLI ανάκτηση. pages=%s records=%s", value["pages"], value["records"])), timeout=3600)
                        rows = dataset.filtered(**documents.get("filters", {}))
                        opened = documents.get("open_document")
                        if opened is not None:
                            if not 1 <= opened <= len(rows) or not DocumentFields.safe_url(rows[opened - 1].get("url")):
                                raise ValueError("Δεν υπάρχει διαθέσιμο URL για τον επιλεγμένο αριθμό.")
                            if not webbrowser.open(rows[opened - 1]["url"], new=2):
                                raise ValueError("Δεν ήταν δυνατό το άνοιγμα του browser.")
                        return {**result, **verified.to_dict(), "success": True,
                            "date_from": dataset.date_from, "date_to": dataset.date_to,
                            "loaded_at": dataset.loaded_at, "summary": dataset.summary(),
                            "complete": dataset.complete, "warning": dataset.warning,
                            "completion_inferred": dataset.completion_inferred,
                            "completion_verified": dataset.completion_verified,
                            "completion_note": dataset.completion_note,
                            "visible_records": len(rows), "documents": rows,
                            "diagnostics": [row.to_dict() for row in service.diagnostics.entries()]}
                    response = await asyncio.to_thread(service.probe, verified, cancel)
                    return {**result, **verified.to_dict(), "success": True, "probe": response,
                            "diagnostics": [row.to_dict() for row in service.diagnostics.entries()]}
                except ProviderAPIError as exc:
                    return {**result, "success": False, "error": exc.message,
                            "error_category": exc.category.value,
                            "diagnostics": [row.to_dict() for row in service.diagnostics.entries()]}
                finally:
                    cancel.set()
                    service.close()
        finally:
            cancel.set()
            session.clear()

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
        parser = self.parser()
        args = parser.parse_args(argv)
        if (args.probe or args.documents or args.issuer_vat) and not args.client:
            parser.error("Τα --probe, --documents και --issuer-vat απαιτούν --client.")
        if (args.open_document is not None or args.series or args.number or args.invoice_type or args.mark) and not args.documents:
            parser.error("Τα φίλτρα παραστατικών και --open-document απαιτούν --documents.")
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        try:
            if args.sections:
                result = {"phase": 2, "sections": SECTIONS}
            elif args.diagnostics_file:
                result = {"scope": "Το επιλεγμένο export· δεν διαβάζεται η RAM άλλου Dashboard process.",
                          "diagnostics": self.diagnostics(args)}
            else:
                options = {"date_from": args.date_from, "date_to": args.date_to,
                    "filters": {"series": args.series, "number": args.number,
                        "invoice_type": args.invoice_type, "mark": args.mark},
                    "open_document": args.open_document} if args.documents else None
                if options is None:
                    result = asyncio.run(self.context(config, args.client, args.bo_connection, args.issuer_vat, args.probe))
                else:
                    result = asyncio.run(self.context(config, args.client, args.bo_connection, args.issuer_vat,
                        args.probe, documents=options))
            text = json.dumps(SECRET_REDACTOR.redact_object(result), ensure_ascii=False, indent=2)
            if args.output:
                args.output.write_text(text + "\n", encoding="utf-8")
            else:
                print(text)
            logger.info("CLI Provider Diagnostic Center ολοκληρώθηκε.")
            if isinstance(result, dict) and result.get("success") is False:
                return 1
            return 2 if isinstance(result, dict) and result.get("complete") is False else 0
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
