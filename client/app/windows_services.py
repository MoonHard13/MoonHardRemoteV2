import subprocess
import csv
import io
import ctypes


class WindowsServicesReader:
    """
    Διαβάζει Windows services από τον client υπολογιστή.
    """

    def _is_running_as_admin(self) -> bool:
        """
        Ελέγχει αν ο client τρέχει με δικαιώματα Administrator.
        """

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

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
        
    def restart_service(self, service_name: str) -> dict:
        """
        Κάνει restart ένα Windows service με βάση το service name.
        """

        if not service_name:
            raise ValueError("Service name is empty.")

        if not self._is_running_as_admin():
            raise PermissionError(
                "Restarting Windows services requires Administrator rights. "
                "Please run the MoonHard client as Administrator."
            )

        safe_service_name = service_name.replace("'", "''")

        powershell_script = (
            f"$name = '{safe_service_name}'; "
            "$service = Get-Service -Name $name -ErrorAction Stop; "
            "Restart-Service -Name $name -Force -ErrorAction Stop; "
            "Start-Sleep -Seconds 2; "
            "$service = Get-Service -Name $name -ErrorAction Stop; "
            "[PSCustomObject]@{"
            "Name=$service.Name;"
            "DisplayName=$service.DisplayName;"
            "Status=$service.Status.ToString()"
            "} | ConvertTo-Json -Compress"
        )

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            powershell_script
        ]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60
        )

        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Failed to restart service.")

        return {
            "success": True,
            "service_name": service_name,
            "message": f"Service restarted successfully: {service_name}",
            "output": completed.stdout.strip()
        }