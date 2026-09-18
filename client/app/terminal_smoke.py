"""Έλεγχος πραγματικών μόνιμων shells μέσα από το συσκευασμένο Client EXE."""

import asyncio
import json
from pathlib import Path

from app.terminal_session import PersistentShell


class ClientTerminalSmokeTest:
    """Εκτελεί τοπικές διαγνωστικές εντολές χωρίς σύνδεση στον Server."""

    @staticmethod
    async def run(report_path: str) -> int:
        """Ελέγχει μεταβλητές, ελληνική έξοδο και native exit code για κάθε shell."""
        checks = []
        try:
            for name in ('cmd', 'powershell'):
                shell = PersistentShell(name)
                chunks = []
                async def emit(text):
                    chunks.append(text)
                try:
                    await shell.start()
                    await shell.execute('set MH_SMOKE=MoonHard' if name == 'cmd' else '$mh_smoke_value = "Ελλάδα"', emit)
                    result = await shell.execute('echo %MH_SMOKE%' if name == 'cmd' else 'Write-Output $mh_smoke_value', emit)
                    assert result['exit_code'] == 0
                    assert ('MoonHard' if name == 'cmd' else 'Ελλάδα') in ''.join(chunks)
                    result = await shell.execute('cmd /c exit 7', emit)
                    assert result['exit_code'] == 7
                    checks.append({'shell':name, 'persistent_variable':True, 'native_exit_code':True})
                finally:
                    await shell.close()
            report = {'success':True, 'checks':checks}
            code = 0
        except Exception as exc:
            report = {'success':False, 'checks':checks, 'exception':type(exc).__name__, 'message':str(exc)}
            code = 1
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return code
