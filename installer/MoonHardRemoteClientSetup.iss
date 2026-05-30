#include "secrets\client_token.iss"

[Setup]
AppId={{8C7C9E7D-5E4A-4B6E-8C3A-1F7E51A01001}
AppName=MoonHard Remote Client
AppVersion=1.0.0
AppPublisher=MoonHard
DefaultDirName={autopf}\MoonHardRemoteV2\Client
DefaultGroupName=MoonHard Remote
OutputDir=output
OutputBaseFilename=MoonHardRemoteClientSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
DisableDirPage=yes
UninstallDisplayName=MoonHard Remote Client
SetupLogging=yes

[Dirs]
Name: "{commonappdata}\MoonHardRemoteV2"; Permissions: system-full admins-full users-readexec
Name: "{commonappdata}\MoonHardRemoteV2\logs"; Permissions: system-full admins-full users-modify
Name: "{commonappdata}\MoonHardRemoteV2\updates"; Permissions: system-full admins-full users-readexec
Name: "{commonappdata}\MoonHardRemoteV2\updates\downloads"; Permissions: system-full admins-full users-modify
Name: "{commonappdata}\MoonHardRemoteV2\updates\extracted"; Permissions: system-full admins-full users-modify
Name: "{commonappdata}\MoonHardRemoteV2\updates\backup"; Permissions: system-full admins-full users-modify
Name: "{app}"; Permissions: system-readexec admins-full users-readexec

[Files]
Source: "client_files\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvFilePath: String;
  EnvContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvFilePath := ExpandConstant('{commonappdata}\MoonHardRemoteV2\.env');

    EnvContent :=
      'CLIENT_TOKEN={#ClientToken}' + #13#10 +
      'SERVER_WEBSOCKET_URL=wss://moonhardremotev2.onrender.com/ws/client' + #13#10 +
      'MOONHARD_CLIENT_DATA_DIR=C:\ProgramData\MoonHardRemoteV2' + #13#10;

    SaveStringToFile(EnvFilePath, EnvContent, False);
  end;
end;

[Run]
Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe stop"; Flags: runhidden waituntilterminated; StatusMsg: "Stopping existing MoonHard service..."; Check: FileExists(ExpandConstant('{app}\MoonHardRemoteClientService.exe'))
Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe uninstall"; Flags: runhidden waituntilterminated; StatusMsg: "Removing existing MoonHard service..."; Check: FileExists(ExpandConstant('{app}\MoonHardRemoteClientService.exe'))

Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing MoonHard service..."
Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe start"; Flags: runhidden waituntilterminated; StatusMsg: "Starting MoonHard service..."

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe stop"; Flags: runhidden waituntilterminated
Filename: "{cmd}"; Parameters: "/C cd /d ""{app}"" && MoonHardRemoteClientService.exe uninstall"; Flags: runhidden waituntilterminated

[Icons]
Name: "{group}\MoonHard Remote Client Folder"; Filename: "{app}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"