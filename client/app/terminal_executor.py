import asyncio
import logging
import os
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)


class TerminalExecutor:
    """
    Εκτελεί CMD/PowerShell εντολές στον client υπολογιστή.
    Κρατάει ξεχωριστό current directory για κάθε shell.
    """

    def __init__(self) -> None:
        """
        Αρχικοποιεί τα working directories για cmd και powershell.
        """

        default_dir = Path.home()

        self.current_directories: dict[str, Path] = {
            "cmd": default_dir,
            "powershell": default_dir
        }

    async def execute_command(self, shell: str, command: str) -> dict:
        """
        Εκτελεί μία εντολή και επιστρέφει stdout/stderr/exit_code/current_directory.
        """

        normalized_shell = self._normalize_shell(shell)
        clean_command = command.strip()

        if not clean_command:
            return self._build_result(
                shell=normalized_shell,
                command=command,
                stdout="",
                stderr="Empty command.",
                exit_code=1
            )

        if self._is_cd_command(clean_command):
            return self._handle_cd_command(
                shell=normalized_shell,
                command=clean_command
            )

        return await self._run_process(
            shell=normalized_shell,
            command=clean_command
        )

    def _normalize_shell(self, shell: str) -> str:
        """
        Κανονικοποιεί το shell σε cmd ή powershell.
        """

        shell_lower = str(shell).strip().lower()

        if shell_lower in ("powershell", "ps", "pwsh"):
            return "powershell"

        return "cmd"

    def _is_cd_command(self, command: str) -> bool:
        """
        Ελέγχει αν η εντολή είναι αλλαγή φακέλου.
        """

        command_lower = command.strip().lower()

        return (
            command_lower == "cd"
            or command_lower.startswith("cd ")
            or command_lower.startswith("chdir ")
        )

    def _handle_cd_command(self, shell: str, command: str) -> dict:
        """
        Διαχειρίζεται cd/chdir και ενημερώνει το current directory χωρίς subprocess.
        """

        current_dir = self.current_directories[shell]

        parts = command.split(maxsplit=1)

        if len(parts) == 1:
            return self._build_result(
                shell=shell,
                command=command,
                stdout=str(current_dir),
                stderr="",
                exit_code=0
            )

        target = parts[1].strip().strip('"')

        if not target:
            target_path = current_dir
        else:
            target_path = Path(target)

            if not target_path.is_absolute():
                target_path = current_dir / target_path

        try:
            resolved_path = target_path.resolve()

            if not resolved_path.exists():
                return self._build_result(
                    shell=shell,
                    command=command,
                    stdout="",
                    stderr=f"The system cannot find the path specified: {resolved_path}",
                    exit_code=1
                )

            if not resolved_path.is_dir():
                return self._build_result(
                    shell=shell,
                    command=command,
                    stdout="",
                    stderr=f"Not a directory: {resolved_path}",
                    exit_code=1
                )

            self.current_directories[shell] = resolved_path

            return self._build_result(
                shell=shell,
                command=command,
                stdout=str(resolved_path),
                stderr="",
                exit_code=0
            )

        except Exception as exc:
            logger.exception("Failed to change directory.")

            return self._build_result(
                shell=shell,
                command=command,
                stdout="",
                stderr=str(exc),
                exit_code=1
            )

    async def _run_process(self, shell: str, command: str) -> dict:
        """
        Εκτελεί πραγματική εντολή στο επιλεγμένο shell.
        """

        current_dir = self.current_directories[shell]

        if shell == "powershell":
            process_command = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command
            ]
        else:
            process_command = [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                command
            ]

        logger.info(
            "Executing command. shell=%s cwd=%s command=%s",
            shell,
            current_dir,
            command
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *process_command,
                cwd=str(current_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_bytes, stderr_bytes = await process.communicate()

            stdout = self._decode_output(stdout_bytes)
            stderr = self._decode_output(stderr_bytes)
            exit_code = process.returncode if process.returncode is not None else -1

            return self._build_result(
                shell=shell,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code
            )

        except FileNotFoundError as exc:
            return self._build_result(
                shell=shell,
                command=command,
                stdout="",
                stderr=f"Shell executable not found: {exc}",
                exit_code=1
            )

        except Exception as exc:
            logger.exception("Command execution failed.")

            return self._build_result(
                shell=shell,
                command=command,
                stdout="",
                stderr=str(exc),
                exit_code=1
            )

    def _decode_output(self, output: bytes) -> str:
        """
        Αποκωδικοποιεί stdout/stderr από Windows commands.
        """

        if not output:
            return ""

        for encoding in ("utf-8", "cp737", "cp1253", "cp1252"):
            try:
                return output.decode(encoding, errors="replace")
            except Exception:
                continue

        return output.decode(errors="replace")

    def _build_result(
        self,
        shell: str,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int
    ) -> dict:
        """
        Δημιουργεί ενιαίο αποτέλεσμα εκτέλεσης terminal command.
        """

        return {
            "shell": shell,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "current_directory": str(self.current_directories[shell])
        }
        
    def get_autocomplete_matches(self, shell: str, command_text: str) -> dict:
        """
        Επιστρέφει autocomplete προτάσεις για αρχεία/φακέλους με βάση το current directory.
        """

        normalized_shell = self._normalize_shell(shell)
        current_dir = self.current_directories[normalized_shell]

        raw_text = command_text or ""
        search_token = self._extract_last_token(raw_text)

        token_without_quotes = search_token.strip().strip('"')

        if not token_without_quotes:
            search_dir = current_dir
            prefix = ""
        else:
            token_path = Path(token_without_quotes)

            if token_path.is_absolute():
                search_dir = token_path.parent
                prefix = token_path.name
            else:
                search_dir = (current_dir / token_path.parent).resolve()
                prefix = token_path.name

        matches: list[dict] = []

        try:
            if not search_dir.exists() or not search_dir.is_dir():
                return {
                    "shell": normalized_shell,
                    "command_text": command_text,
                    "search_token": search_token,
                    "matches": [],
                    "current_directory": str(current_dir)
                }

            for item in search_dir.iterdir():
                item_name = item.name

                if not item_name.lower().startswith(prefix.lower()):
                    continue

                display_name = item_name + ("\\" if item.is_dir() else "")

                if " " in display_name:
                    insert_value = f'"{display_name}"'
                else:
                    insert_value = display_name

                matches.append(
                    {
                        "name": item_name,
                        "insert_value": insert_value,
                        "is_dir": item.is_dir(),
                        "full_path": str(item)
                    }
                )

            matches.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))

            return {
                "shell": normalized_shell,
                "command_text": command_text,
                "search_token": search_token,
                "matches": matches[:50],
                "current_directory": str(current_dir)
            }

        except Exception as exc:
            logger.exception("Autocomplete failed.")

            return {
                "shell": normalized_shell,
                "command_text": command_text,
                "search_token": search_token,
                "matches": [],
                "error": str(exc),
                "current_directory": str(current_dir)
            }

    def _extract_last_token(self, command_text: str) -> str:
        """
        Παίρνει το τελευταίο κομμάτι της εντολής για autocomplete.
        Υποστηρίζει απλές εντολές με κενά και quotes.
        """

        text = command_text.rstrip()

        if not text:
            return ""

        if '"' in text:
            last_quote_index = text.rfind('"')

            if last_quote_index != -1:
                before_last_quote = text[:last_quote_index]
                previous_quote_index = before_last_quote.rfind('"')

                if previous_quote_index != -1:
                    return text[previous_quote_index + 1:last_quote_index]

        parts = text.split()

        if not parts:
            return ""

        return parts[-1]