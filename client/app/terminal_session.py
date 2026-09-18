"""Μόνιμα shells με περιορισμένη έξοδο, χρονικό όριο και καθαρό τερματισμό."""

import asyncio
import base64
import codecs
import json
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path


logger = logging.getLogger(__name__)


class OutputFramer:
    """Ξεχωρίζει το τελικό πλαίσιο ακόμη και όταν χωρίζεται σε πολλά πακέτα."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.buffer = ""
        self.result = None

    def feed(self, text: str) -> str:
        """Αποδίδει αμέσως την έξοδο κρατώντας μόνο το πιθανό τελικό πλαίσιο."""
        self.buffer += text
        position = self.buffer.find(self.token + ":")
        if position >= 0:
            output, footer = self.buffer[:position], self.buffer[position:]
            if "\n" in footer:
                line, self.buffer = footer.split("\n", 1)
                _, exit_code, directory = line.rstrip("\r").split(":", 2)
                self.result = (int(exit_code), directory.strip('"'))
            else:
                self.buffer = footer
            return output
        marker = self.token + ":"
        retained = 0
        for size in range(min(len(marker), len(self.buffer)), 0, -1):
            if self.buffer.endswith(marker[:size]):
                retained = size
                break
        if retained:
            output, self.buffer = self.buffer[:-retained], self.buffer[-retained:]
        else:
            output, self.buffer = self.buffer, ""
        return output


class PersistentShell:
    """Διατηρεί ένα process ανά συνεδρία, χωρίς προσομοίωση των εντολών cd/set."""

    MAX_OUTPUT = 60000
    TIMEOUT = 60
    PS_INIT = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); $OutputEncoding = [Console]::OutputEncoding\n\n"

    def __init__(self, shell: str) -> None:
        self.shell = shell
        self.directory = str(Path.home())
        self.process = None
        self.busy = False
        self.closed = False
        self.stopped = False

    async def start(self) -> None:
        """Ξεκινά το shell χωρίς παράθυρο κονσόλας στον απομακρυσμένο υπολογιστή."""
        if os.name != "nt":
            raise RuntimeError("Οι μόνιμες συνεδρίες Terminal απαιτούν Windows στον Client.")
        if self.shell == "powershell":
            args = ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-Command", "-"]
        else:
            args = ["cmd.exe", "/d", "/q", "/k", "chcp 65001>nul & prompt $s"]
        self.process = await asyncio.create_subprocess_exec(
            *args, cwd=self.directory, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if self.shell == "powershell":
            self.process.stdin.write(self.PS_INIT.encode("ascii"))
            await self.process.stdin.drain()
        logger.info("Εκκίνηση μόνιμου shell. shell=%s pid=%s", self.shell, self.process.pid)

    def script(self, command: str, token: str) -> bytes:
        """Κωδικοποιεί εντολή και πλαίσιο ολοκλήρωσης χωρίς αλλαγή της σύνταξης shell."""
        if self.shell == "powershell":
            encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
            script = (
                "$LASTEXITCODE = 0; try { "
                ". ([scriptblock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')))) | Out-Default; "
                "$mh_ok = $?; $mh_code = if ($LASTEXITCODE -ne 0) { $LASTEXITCODE } elseif ($mh_ok) { 0 } else { 1 } "
                "} catch { $_ | Out-String | ForEach-Object { [Console]::Write($_) }; $mh_code = 1 }; "
                "[Console]::WriteLine('" + token + ":' + $mh_code + ':' + (Get-Location).Path)\n\n"
            )
            return script.encode("ascii")
        return (command + '\r\n@echo ' + token + ':%errorlevel%:"%cd%"\r\n').encode("utf-8")

    async def execute(self, command: str, emit) -> dict:
        """Αποστέλλει σταδιακά έξοδο και επιστρέφει πραγματικό directory και exit code."""
        if self.busy:
            raise ValueError("Εκτελείται ήδη εντολή στη συνεδρία.")
        if self.closed or not self.process or self.process.returncode is not None:
            raise ValueError("Η συνεδρία έκλεισε. Πατήστε Reconnect.")
        if not isinstance(command, str) or not command.strip() or len(command) > 8000:
            raise ValueError("Η εντολή πρέπει να έχει 1–8000 χαρακτήρες.")
        if "\n" in command or "\r" in command or "\x00" in command:
            raise ValueError("Εκτελέστε μία γραμμή εντολής κάθε φορά.")
        self.busy = True
        started = time.monotonic()
        framer = OutputFramer("__MH_" + uuid.uuid4().hex)
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        count = 0
        truncated = False

        async def output(text: str) -> None:
            """Περιορίζει το αποστελλόμενο κείμενο ενώ συνεχίζει να αδειάζει τον σωλήνα."""
            nonlocal count, truncated
            remaining = max(0, self.MAX_OUTPUT - count)
            if text and remaining:
                chunk = text[:remaining]
                count += len(chunk)
                await emit(chunk)
            if len(text) > remaining and not truncated:
                truncated = True
                await emit("\n[Η έξοδος περιορίστηκε στους 60.000 χαρακτήρες.]\n")

        try:
            self.process.stdin.write(self.script(command, framer.token))
            await self.process.stdin.drain()

            async def read() -> tuple:
                """Διαβάζει μικρά πακέτα χωρίς να περιμένει αλλαγή γραμμής."""
                while framer.result is None:
                    chunk = await self.process.stdout.read(4096)
                    if not chunk:
                        await output(framer.feed(decoder.decode(b"", final=True)))
                        await output(framer.buffer)
                        self.closed = True
                        await self.process.wait()
                        return (130 if self.stopped else self.process.returncode, self.directory)
                    await output(framer.feed(decoder.decode(chunk)))
                return framer.result

            try:
                exit_code, self.directory = await asyncio.wait_for(read(), self.TIMEOUT)
            except asyncio.TimeoutError:
                await self.close()
                exit_code = 124
                await emit("\n[Η εντολή υπερέβη τα 60 δευτερόλεπτα. Η συνεδρία έκλεισε.]\n")
            return {"exit_code": exit_code, "current_directory": self.directory,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "session_closed": self.closed, "truncated": truncated}
        except asyncio.CancelledError:
            await self.close()
            raise
        finally:
            self.busy = False

    async def close(self) -> None:
        """Τερματίζει το shell και τα θυγατρικά processes, ακόμη και αν έχει ήδη εξέλθει."""
        self.closed = True
        process = self.process
        if not process:
            return
        if process.returncode is None:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec(
                    "taskkill.exe", "/PID", str(process.pid), "/T", "/F",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                try:
                    await asyncio.wait_for(killer.wait(), 5)
                except asyncio.TimeoutError:
                    killer.kill()
                    await killer.wait()
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
        logger.info("Τερματισμός μόνιμου shell. shell=%s pid=%s", self.shell, process.pid)


class TerminalSessionManager:
    """Εκτελεί ανεξάρτητα tasks ώστε το Stop και τα heartbeat να παραμένουν διαθέσιμα."""

    def __init__(self) -> None:
        self.sessions = {}
        self.tasks = {}

    async def handle(self, websocket, payload: dict, client_code: str) -> None:
        """Εξυπηρετεί εντολές συνεδρίας χωρίς καταγραφή περιεχομένου εντολών ή εξόδου."""
        session_id = payload.get("session_id", "")
        request_id = payload.get("request_id", "")
        kind = payload["type"]
        base = {"session_id": session_id, "request_id": request_id, "client_code": client_code}

        async def send(kind: str, **fields) -> None:
            """Αποστέλλει απάντηση μόνο στην τρέχουσα σύνδεση."""
            await websocket.send(json.dumps({**base, "type": kind, **fields}, ensure_ascii=False))

        try:
            if kind == "terminal_session_open":
                if session_id in self.sessions or len(self.sessions) >= 8:
                    raise ValueError("Υπάρχει ήδη η συνεδρία ή έχει συμπληρωθεί το όριο συνεδριών.")
                shell = payload.get("shell", "cmd")
                if shell not in ("cmd", "powershell"):
                    raise ValueError("Μη έγκυρο shell.")
                session = PersistentShell(shell)
                self.sessions[session_id] = session
                try:
                    await session.start()
                    result = await asyncio.wait_for(session.execute("cd" if shell == "cmd" else "Get-Location | Out-Null", lambda _: asyncio.sleep(0)), 10)
                except BaseException:
                    self.sessions.pop(session_id, None)
                    await session.close()
                    raise
                await send("terminal_session_result", operation="open", success=True, shell=shell, **result)
            elif kind == "terminal_session_close":
                session = self.sessions.pop(session_id, None)
                if session:
                    await session.close()
            else:
                session = self.sessions.get(session_id)
                if not session:
                    raise ValueError("Η συνεδρία δεν υπάρχει. Πατήστε Reconnect.")
                if kind == "terminal_session_stop":
                    session.stopped = True
                    await session.close()
                    return
                if session.busy or session_id in self.tasks:
                    raise ValueError("Εκτελείται ήδη εντολή στη συνεδρία.")

                async def execute() -> None:
                    """Απομονώνει την εκτέλεση ώστε ο κεντρικός listener να συνεχίζει να ακούει."""
                    try:
                        result = await session.execute(payload.get("command", ""),
                            lambda text: send("terminal_session_output", text=text))
                        await send("terminal_session_result", operation="command", success=True, **result)
                    except Exception as exc:
                        await session.close()
                        await send("terminal_session_result", operation="command", success=False,
                                   message=str(exc), session_closed=True)
                    finally:
                        self.tasks.pop(session_id, None)
                        if session.closed:
                            self.sessions.pop(session_id, None)

                self.tasks[session_id] = asyncio.create_task(execute())
                logger.info("Εκτέλεση Terminal. session_id=%s request_id=%s", session_id, request_id)
        except Exception as exc:
            logger.warning("Αποτυχία Terminal. operation=%s exception=%s", kind, type(exc).__name__)
            await send("terminal_session_result", operation="open" if kind.endswith("open") else "command",
                       success=False, message=str(exc), session_closed=True)

    async def close_all(self) -> None:
        """Καθαρίζει όλες τις συνεδρίες και τα tasks σε αποσύνδεση ή έξοδο του Client."""
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await asyncio.gather(*(session.close() for session in self.sessions.values()), return_exceptions=True)
        self.tasks.clear()
        self.sessions.clear()
