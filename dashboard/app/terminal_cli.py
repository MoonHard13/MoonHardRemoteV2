"""Χρήση των ίδιων μόνιμων συνεδριών Terminal από CMD/PowerShell."""

import argparse
import asyncio
import json
import logging
import sys
import threading
import uuid

import websockets

from app.config import DashboardConfig
from app.logger_config import DashboardLoggerConfig


logger = logging.getLogger(__name__)


class TerminalCLI:
    """Εκτελεί διαδοχικές εντολές στο ίδιο remote shell, με ζωντανή έξοδο."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        """Ορίζει Client, shell και μία ή περισσότερες διαδοχικές εντολές."""
        parser = argparse.ArgumentParser(description="Μόνιμο απομακρυσμένο Terminal MoonHard.")
        parser.add_argument("--client", required=True, help="Κωδικός Client.")
        parser.add_argument("--shell", choices=("cmd", "powershell"), default="cmd")
        parser.add_argument("--command", action="append", help="Μία εντολή· επαναλάβετε για κοινή συνεδρία.")
        parser.add_argument("--interactive", action="store_true", help="Εισαγωγή διαδοχικών εντολών στο τοπικό CMD.")
        return parser

    @staticmethod
    async def read_command(prompt: str) -> str:
        """Διαβάζει stdin σε daemon thread ώστε το Ctrl+C να μη μπλοκάρει το shutdown."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        def read():
            try:
                result, error = input(prompt), None
            except BaseException as exc:
                result, error = None, exc
            def deliver():
                if not future.done():
                    if error:
                        future.set_exception(error)
                    else:
                        future.set_result(result)
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(deliver)
                except RuntimeError:
                    pass
        threading.Thread(target=read, daemon=True).start()
        return await future

    async def run_session(self, config, args) -> int:
        """Αυθεντικοποιείται και κλείνει τη συνεδρία σε έξοδο, σφάλμα ή Ctrl+C."""
        if not config.dashboard_token:
            raise ValueError("Δεν έχει οριστεί DASHBOARD_TOKEN.")
        session_id = str(uuid.uuid4())
        async with websockets.connect(config.dashboard_websocket_url, open_timeout=15, close_timeout=5) as ws:
            await ws.send(json.dumps({"type": "authenticate", "token": config.dashboard_token}))
            while True:
                reply = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if reply.get("type") == "dashboard_connected":
                    break
                if reply.get("type") == "error":
                    raise ValueError("Απέτυχε η αυθεντικοποίηση.")

            async def send(kind, request_id, **fields):
                """Χρησιμοποιεί το ίδιο περίβλημα συνεδρίας με το GUI."""
                await ws.send(json.dumps({"type": kind, "client_code": args.client,
                    "session_id": session_id, "request_id": request_id, **fields}, ensure_ascii=False))

            async def receive(request_id):
                """Εμφανίζει output άμεσα και αγνοεί απαντήσεις άλλων αιτημάτων."""
                while True:
                    result = json.loads(await ws.recv())
                    if (result.get("session_id") != session_id or result.get("request_id") != request_id
                            or result.get("client_code") != args.client):
                        continue
                    if result.get("type") == "terminal_session_output":
                        print(result.get("text", ""), end="", flush=True)
                    elif result.get("type") == "terminal_session_result":
                        if not result.get("success"):
                            raise ValueError(result.get("message", "Αποτυχία Terminal."))
                        return result

            async def execute(command):
                """Εκτελεί μία γραμμή χωρίς να καταγράφει το περιεχόμενό της στο log."""
                request_id = str(uuid.uuid4())
                await send("terminal_session_command", request_id, command=command)
                logger.info("Εκτέλεση CLI Terminal. client=%s request_id=%s", args.client, request_id)
                return await asyncio.wait_for(receive(request_id), 80)

            try:
                request_id = str(uuid.uuid4())
                await send("terminal_session_open", request_id, shell=args.shell)
                result = await asyncio.wait_for(receive(request_id), 18)
                for command in args.command or []:
                    result = await execute(command)
                    if result.get("session_closed"):
                        break
                if args.interactive and not result.get("session_closed"):
                    while True:
                        prompt = ("PS " if args.shell == "powershell" else "") + result.get("current_directory", "") + "> "
                        try:
                            command = await self.read_command(prompt)
                        except EOFError:
                            break
                        if command == ":quit":
                            break
                        if command == ":clear":
                            print("\033[2J\033[H", end="", flush=True)
                            continue
                        if command == ":help":
                            print(":quit = έξοδος, :clear = καθαρισμός προβολής, Ctrl+C = τερματισμός συνεδρίας.")
                            continue
                        if not command.strip():
                            continue
                        result = await execute(command)
                        if result.get("session_closed"):
                            break
                return int(result.get("exit_code", 0))
            finally:
                if ws.state.name == "OPEN":
                    await send("terminal_session_close", str(uuid.uuid4()))

    def run(self, argv=None) -> int:
        """Επιστρέφει πραγματικό exit code ή σαφές μήνυμα αποτυχίας."""
        parser = self.parser()
        args = parser.parse_args(argv)
        if not args.command and not args.interactive:
            parser.error("Δώστε --command ή --interactive.")
        config = DashboardConfig()
        DashboardLoggerConfig.setup_logging(config.log_dir)
        for handler in logging.getLogger().handlers:
            if type(handler) is logging.StreamHandler:
                handler.setStream(sys.stderr)
        try:
            return asyncio.run(self.run_session(config, args))
        except KeyboardInterrupt:
            print("\nΗ συνεδρία τερματίστηκε.", file=sys.stderr)
            return 130
        except Exception as exc:
            logger.error("Αποτυχία CLI Terminal. exception=%s", type(exc).__name__)
            print(str(exc) if isinstance(exc, ValueError) else "Αποτυχία σύνδεσης ή λήξη αναμονής Terminal.", file=sys.stderr)
            return 1


def main(argv=None) -> int:
    """Σημείο εισόδου για python -m και το εκτελέσιμο Dashboard."""
    return TerminalCLI().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
