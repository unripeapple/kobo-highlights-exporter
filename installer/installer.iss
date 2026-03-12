[Setup]
AppName=Kobo Highlights Exporter
AppVersion=1.0.0
DefaultDirName={autopf}\Kobo Highlights Exporter
DefaultGroupName=Kobo Highlights Exporter
OutputDir=..\dist_installer
OutputBaseFilename=KoboHighlightsExporter_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\Kobo Highlights Exporter.exe
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Files]
; Copy app files
Source: "..\dist\Kobo Highlights Exporter\*"; DestDir: "{app}"; Flags: recursesubdirs

; Include Visual C++ v14 x64 Redistributable
Source: "..\assets\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Kobo Highlights Exporter"; Filename: "{app}\Kobo Highlights Exporter.exe"
Name: "{autodesktop}\Kobo Highlights Exporter"; Filename: "{app}\Kobo Highlights Exporter.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
; Install Visual C++ runtime silently
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ Runtime..."; Flags: waituntilterminated

; Launch app after installation
Filename: "{app}\Kobo Highlights Exporter.exe"; Description: "Launch Kobo Highlights Exporter"; Flags: nowait postinstall skipifsilent
