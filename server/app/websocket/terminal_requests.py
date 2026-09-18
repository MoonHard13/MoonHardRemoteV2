"""Δρομολόγηση ιδιωτικών συνεδριών Terminal με έλεγχο ιδιοκτησίας και χρονικά όρια."""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID


logger = logging.getLogger(__name__)


@dataclass
class TerminalRoute:
    """Κρατά μόνο αναγνωριστικά και το dashboard που άνοιξε τη συνεδρία."""

    dashboard: object
    client_code: str
    shell: str
    request_id: str = ""
    operation: str = "open"
    timer: object = None
    ready: bool = False


class TerminalRequestRouter:
    """Δεν μεταδίδει ποτέ εντολές ή output σε άλλα dashboards."""

    REQUEST_TYPES = {"terminal_session_open", "terminal_session_command", "terminal_session_stop", "terminal_session_close"}
    RESULT_TYPES = {"terminal_session_result", "terminal_session_output"}

    def __init__(self, manager) -> None:
        self.manager = manager
        self.sessions = {}

    async def error(self, dashboard, data: dict, message: str) -> None:
        """Επιστρέφει αποτυχία με το αρχικό αναγνωριστικό για ορθή συσχέτιση."""
        await self.manager.send_to_dashboard(dashboard, {
            "type": "terminal_session_result", "operation": "open" if data.get("type") == "terminal_session_open" else "command",
            "session_id": data.get("session_id", ""), "request_id": data.get("request_id", ""),
            "client_code": data.get("client_code", ""), "success": False, "message": message,
            "session_closed": True,
        })

    def remove(self, session_id: str):
        """Αφαιρεί τη συσχέτιση και ακυρώνει το χρονόμετρο."""
        route = self.sessions.pop(session_id, None)
        if route and route.timer:
            route.timer.cancel()
        return route

    async def request(self, dashboard, data: dict) -> None:
        """Ελέγχει τύπους, UUID, όρια και δυνατότητες του Client πριν την προώθηση."""
        kind = data["type"]
        session_id = data.get("session_id", "")
        request_id = data.get("request_id", "")
        code = data.get("client_code", "")
        try:
            UUID(session_id)
            UUID(request_id)
            if not isinstance(code, str) or not 1 <= len(code) <= 128:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            await self.error(dashboard, data, "Μη έγκυρα στοιχεία συνεδρίας.")
            return
        route = self.sessions.get(session_id)
        if kind == "terminal_session_open":
            if route or sum(r.dashboard is dashboard for r in self.sessions.values()) >= 8 or len(self.sessions) >= 256:
                await self.error(dashboard, data, "Η συνεδρία υπάρχει ήδη ή συμπληρώθηκε το όριο συνεδριών.")
                return
            shell = data.get("shell", "cmd")
            if shell not in ("cmd", "powershell"):
                await self.error(dashboard, data, "Μη έγκυρο shell.")
                return
            if not self.manager.client_supports(code, "terminal_session_v1"):
                await self.error(dashboard, data, "Ο Client χρειάζεται ενημέρωση για το νέο Terminal ή είναι offline.")
                return
            route = TerminalRoute(dashboard, code, shell)
            self.sessions[session_id] = route
        elif not route or route.dashboard is not dashboard or route.client_code != code:
            await self.error(dashboard, data, "Η συνεδρία δεν ανήκει σε αυτή τη σύνδεση ή έχει κλείσει.")
            return
        if kind == "terminal_session_command":
            command = data.get("command")
            if not isinstance(command, str) or not command.strip() or len(command) > 8000 or any(c in command for c in "\r\n\x00"):
                await self.error(dashboard, data, "Δώστε μία γραμμή εντολής με έως 8000 χαρακτήρες.")
                return
            if not route.ready or route.request_id:
                await self.error(dashboard, data, "Η συνεδρία δεν είναι έτοιμη ή εκτελείται ήδη εντολή.")
                return
        if kind == "terminal_session_stop" and (not route.request_id or route.operation != "command"):
            return
        if kind in ("terminal_session_open", "terminal_session_command"):
            route.request_id = request_id
            route.operation = "open" if kind.endswith("open") else "command"
            route.timer = asyncio.get_running_loop().call_later(
                15 if kind.endswith("open") else 75,
                lambda: asyncio.create_task(self.expire(session_id)),
            )
        forwarded = {key: data[key] for key in ("type", "session_id", "request_id", "client_code", "shell", "command") if key in data}
        try:
            sent = await self.manager.send_to_client(code, forwarded)
        except Exception:
            sent = False
        if kind == "terminal_session_close":
            self.remove(session_id)
        elif not sent:
            self.remove(session_id)
            await self.error(dashboard, data, "Ο Client δεν είναι συνδεδεμένος.")
        logger.info("Αίτημα Terminal. type=%s session_id=%s", kind, session_id)

    async def result(self, client_code: str, data: dict) -> None:
        """Δέχεται μόνο την αναμενόμενη απάντηση από τον αυθεντικοποιημένο Client."""
        session_id = data.get("session_id")
        if not isinstance(session_id, str):
            return
        route = self.sessions.get(session_id)
        if not route or route.client_code != client_code or not route.request_id or route.request_id != data.get("request_id"):
            return
        if data["type"] == "terminal_session_output":
            text = data.get("text")
            if route.operation != "command" or not isinstance(text, str) or len(text) > 8192:
                return
        else:
            if data.get("operation") != route.operation:
                return
            if route.timer:
                route.timer.cancel()
            route.request_id = ""
            route.ready = bool(data.get("success")) and not data.get("session_closed")
            if not route.ready:
                self.remove(session_id)
        await self.manager.send_to_dashboard(route.dashboard, {**data, "client_code": client_code})

    async def close_client_session(self, session_id: str, route) -> None:
        """Ζητά κλείσιμο του shell χωρίς γενική εκπομπή των δεδομένων του."""
        try:
            await self.manager.send_to_client(route.client_code, {
                "type": "terminal_session_close", "session_id": session_id,
                "request_id": session_id, "client_code": route.client_code,
            })
        except Exception:
            logger.warning("Αποτυχία αποστολής κλεισίματος Terminal. session_id=%s", session_id)

    async def expire(self, session_id: str) -> None:
        """Κλείνει την αναμονή και το shell όταν δεν υπάρχει έγκαιρη τελική απάντηση."""
        route = self.remove(session_id)
        if route:
            await self.close_client_session(session_id, route)
            await self.error(route.dashboard, {
                "type": "terminal_session_" + route.operation, "session_id": session_id,
                "request_id": route.request_id, "client_code": route.client_code,
            }, "Δεν ελήφθη απάντηση εγκαίρως. Ελέγξτε σύνδεση και ενημέρωση Server/Client.")

    async def discard_dashboard(self, dashboard) -> None:
        """Κλείνει όλα τα shells του dashboard όταν χαθεί η σύνδεσή του."""
        for session_id, route in list(self.sessions.items()):
            if route.dashboard is dashboard:
                self.remove(session_id)
                await self.close_client_session(session_id, route)

    async def discard_client(self, client_code: str) -> None:
        """Ενημερώνει το ιδιοκτήτη κάθε συνεδρίας όταν ο Client αποσυνδεθεί."""
        for session_id, route in list(self.sessions.items()):
            if route.client_code == client_code:
                self.remove(session_id)
                try:
                    await self.error(route.dashboard, {"session_id": session_id, "request_id": route.request_id,
                                     "client_code": client_code}, "Ο Client αποσυνδέθηκε. Πατήστε Reconnect όταν συνδεθεί.")
                except Exception:
                    logger.warning("Το dashboard της συνεδρίας δεν είναι διαθέσιμο.")
