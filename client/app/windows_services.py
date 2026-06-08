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
    MOONHARD_SERVICE_DISPLAY_NAME = "MoonHard Remote Client"

    def _is_running_as_admin(self) -> bool:
        """
        Ελέγχει αν ο client τρέχει με δικαιώματα Administrator.
        """

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _is_moonhard_service(self, service_name: str) -> bool:
        """
        Ελέγχει αν το επιλεγμένο service είναι το MoonHard service
        είτε με βάση το service id είτε με βάση το display name.
        """

        normalized_name = str(service_name or "").strip().lower()

        return normalized_name in {
            self.MOONHARD_SERVICE_NAME.lower(),
            self.MOONHARD_SERVICE_DISPLAY_NAME.lower()
        }

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

        if self._is_moonhard_service(service_name):
            return self._schedule_self_service_restart(self.MOONHARD_SERVICE_NAME)

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
        Το restart εκτελείται από Windows Scheduled Task ως SYSTEM,
        ώστε να μη σκοτωθεί μαζί με το client process.
        """

        safe_service_name = service_name.replace("'", "''")
        script_path = Path(tempfile.gettempdir()) / "moonhard_self_restart.ps1"
        launch_log_path = Path(tempfile.gettempdir()) / "moonhard_self_restart_launch.log"
        task_name = "MoonHardRemoteClientSelfRestart"

        powershell_script = f"""
$ErrorActionPreference = 'Stop'

$serviceName = '{safe_service_name}'
$programDataPath = [Environment]::GetFolderPath('CommonApplicationData')
$logFile = Join-Path $programDataPath 'MoonHardRemoteV2\\logs\\self_restart.log'

try {{
    New-Item -ItemType Directory -Path (Split-Path $logFile) -Force | Out-Null

    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Scheduled self restart script started for $serviceName"

    Start-Sleep -Seconds 5

    $service = Get-Service -Name $serviceName -ErrorAction Stop
    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Current status before stop: $($service.Status)"

    if ($service.Status -ne 'Stopped') {{
        Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Stopping $serviceName"
        Stop-Service -Name $serviceName -Force -ErrorAction Stop
        Start-Sleep -Seconds 8
    }}

    $service = Get-Service -Name $serviceName -ErrorAction Stop
    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Status after stop command: $($service.Status)"

    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting $serviceName"
    Start-Service -Name $serviceName -ErrorAction Stop

    Start-Sleep -Seconds 8

    $service = Get-Service -Name $serviceName -ErrorAction Stop
    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Final status: $($service.Status)"

    Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Scheduled self restart completed for $serviceName"
}}
catch {{
    try {{
        New-Item -ItemType Directory -Path (Split-Path $logFile) -Force | Out-Null
        Add-Content -Path $logFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Scheduled self restart failed for $($serviceName): $($_.Exception.Message)"
    }}
    catch {{
    }}
}}
"""

        script_path.write_text(powershell_script, encoding="utf-8")

        launch_log_path.write_text(
            f"Created script: {script_path}\n"
            f"Target service: {service_name}\n"
            f"Task name: {task_name}\n",
            encoding="utf-8"
        )

        task_time = "23:59"
        task_command = (
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass '
            f'-File "{script_path}"'
        )

        create_task = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                task_name,
                "/TR",
                task_command,
                "/SC",
                "ONCE",
                "/ST",
                task_time,
                "/RU",
                "SYSTEM",
                "/RL",
                "HIGHEST",
                "/F"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )

        if create_task.returncode != 0:
            raise RuntimeError(
                create_task.stderr.strip()
                or create_task.stdout.strip()
                or "Failed to create self-restart scheduled task."
            )

        run_task = subprocess.run(
            [
                "schtasks",
                "/Run",
                "/TN",
                task_name
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )

        if run_task.returncode != 0:
            raise RuntimeError(
                run_task.stderr.strip()
                or run_task.stdout.strip()
                or "Failed to run self-restart scheduled task."
            )

        return {
            "success": True,
            "service_name": service_name,
            "message": (
                "MoonHard service self-restart scheduled task was created and started. "
                "The client should disconnect briefly and reconnect automatically."
            ),
            "output": (
                f"Script: {script_path}\n"
                f"Launch log: {launch_log_path}\n"
                f"Task name: {task_name}\n"
                "Expected service log: C:\\ProgramData\\MoonHardRemoteV2\\logs\\self_restart.log"
            )
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