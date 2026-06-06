import subprocess
import csv
import io
import ctypes
import tempfile
from pathlib import Path


class WindowsServicesReader:
    """
    Διαβάζει Windows services από τον client υπολογιστή.
    """

    MOONHARD_SERVICE_NAME = "MoonHardRemoteClient"

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

        if service_name.lower() == self.MOONHARD_SERVICE_NAME.lower():
            return self._schedule_self_service_restart(service_name)

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

    def _schedule_self_service_restart(self, service_name: str) -> dict:
        """
        Προγραμματίζει ασφαλές restart του ίδιου του MoonHard service.
        Το restart γίνεται από ξεχωριστό detached PowerShell process,
        ώστε να μην σκοτωθεί ο client πριν ξεκινήσει ξανά το service.
        """

        safe_service_name = service_name.replace("'", "''")
        script_path = Path(tempfile.gettempdir()) / "moonhard_self_restart.ps1"

        powershell_script = f"""
Start-Sleep -Seconds 2

$serviceName = '{safe_service_name}'
$logFile = Join-Path $env:ProgramData 'MoonHardRemoteV2\\logs\\self_restart.log'

try {{
    New-Item -ItemType Directory -Path (Split-Path $logFile) -Force | Out-Null

    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Self restart started for $serviceName"

    $service = Get-Service -Name $serviceName -ErrorAction Stop

    if ($service.Status -ne 'Stopped') {{
        Stop-Service -Name $serviceName -Force -ErrorAction Stop
        $service.WaitForStatus('Stopped', '00:00:30')
    }}

    Start-Sleep -Seconds 2

    Start-Service -Name $serviceName -ErrorAction Stop

    $service = Get-Service -Name $serviceName -ErrorAction Stop
    $service.WaitForStatus('Running', '00:00:30')

    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Self restart completed for $serviceName"
}}
catch {{
    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Self restart failed for $serviceName: $($_.Exception.Message)"
}}
"""
        script_path.write_text(powershell_script, encoding="utf-8")

        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script_path)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        )

        return {
            "success": True,
            "service_name": service_name,
            "message": (
                "MoonHard service self-restart was scheduled. "
                "The client will disconnect briefly and reconnect automatically."
            ),
            "output": str(script_path)
        }
        
    def start_service(self, service_name: str) -> dict:
        """
        Ξεκινάει ένα Windows service με βάση το service name.
        """

        if not service_name:
            raise ValueError("Service name is empty.")

        if not self._is_running_as_admin():
            raise PermissionError(
                "Starting Windows services requires Administrator rights. "
                "Please run the MoonHard client as Administrator."
            )

        safe_service_name = service_name.replace("'", "''")

        powershell_script = (
            f"$name = '{safe_service_name}'; "
            "$service = Get-Service -Name $name -ErrorAction Stop; "
            "Start-Service -Name $name -ErrorAction Stop; "
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
            raise RuntimeError(completed.stderr.strip() or "Failed to start service.")

        return {
            "success": True,
            "service_name": service_name,
            "message": f"Service started successfully: {service_name}",
            "output": completed.stdout.strip()
        }

    def stop_service(self, service_name: str) -> dict:
        """
        Σταματάει ένα Windows service με βάση το service name.
        """

        if not service_name:
            raise ValueError("Service name is empty.")

        if not self._is_running_as_admin():
            raise PermissionError(
                "Stopping Windows services requires Administrator rights. "
                "Please run the MoonHard client as Administrator."
            )

        safe_service_name = service_name.replace("'", "''")

        powershell_script = (
            f"$name = '{safe_service_name}'; "
            "$service = Get-Service -Name $name -ErrorAction Stop; "
            "Stop-Service -Name $name -Force -ErrorAction Stop; "
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
            raise RuntimeError(completed.stderr.strip() or "Failed to stop service.")

        return {
            "success": True,
            "service_name": service_name,
            "message": f"Service stopped successfully: {service_name}",
            "output": completed.stdout.strip()
        }