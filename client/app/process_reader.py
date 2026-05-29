import csv
import io
import subprocess


class ProcessReader:
    """
    Διαβάζει τα running processes από τον client υπολογιστή.
    """

    def get_processes(self) -> dict:
        """
        Επιστρέφει λίστα processes με βασικές πληροφορίες.
        """

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Get-Process | "
                "Select-Object "
                "ProcessName,"
                "Id,"
                "@{Name='CpuTime';Expression={if ($_.CPU -ne $null) {[math]::Round($_.CPU, 2)} else {0}}},"
                "@{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet64 / 1MB, 2)}},"
                "Threads,"
                "Handles,"
                "@{Name='Path';Expression={$_.Path}} | "
                "Sort-Object WorkingSet64 -Descending | "
                "ConvertTo-Csv -NoTypeInformation"
            )
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )

        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Failed to read processes.")

        csv_text = completed.stdout.strip()

        if not csv_text:
            return {
                "success": True,
                "processes": [],
                "count": 0
            }

        reader = csv.DictReader(io.StringIO(csv_text))
        processes: list[dict] = []

        for row in reader:
            processes.append(
                {
                    "name": row.get("ProcessName", ""),
                    "pid": row.get("Id", ""),
                    "cpu_time": row.get("CpuTime", ""),
                    "memory_mb": row.get("MemoryMB", ""),
                    "threads": row.get("Threads", ""),
                    "handles": row.get("Handles", ""),
                    "path": row.get("Path", "")
                }
            )

        return {
            "success": True,
            "processes": processes,
            "count": len(processes)
        }