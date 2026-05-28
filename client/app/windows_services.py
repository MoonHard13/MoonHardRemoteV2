import subprocess
import csv
import io


class WindowsServicesReader:
    """
    Διαβάζει Windows services από τον client υπολογιστή.
    """

    def get_services(self) -> dict:
        """
        Επιστρέφει λίστα Windows services με Name, DisplayName, Status και StartType.
        """

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "Get-CimInstance Win32_Service | "
                "Select-Object Name,DisplayName,State,StartMode | "
                "Sort-Object DisplayName | "
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
            raise RuntimeError(completed.stderr.strip() or "Failed to read Windows services.")

        csv_text = completed.stdout.strip()

        if not csv_text:
            return {
                "success": True,
                "services": [],
                "count": 0
            }

        reader = csv.DictReader(io.StringIO(csv_text))
        services: list[dict] = []

        for row in reader:
            services.append(
                {
                    "name": row.get("Name", ""),
                    "display_name": row.get("DisplayName", ""),
                    "status": row.get("State", ""),
                    "start_type": row.get("StartMode", "")
                }
            )

        return {
            "success": True,
            "services": services,
            "count": len(services)
        }