; installer.iss — Inno Setup 6 script for Meeting Notes AI
;
; Prerequisites:
;   1. Build with PyInstaller first:  pyinstaller app.spec
;   2. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
;   3. Compile this script:  iscc installer.iss
;
; Output: Output\MeetingNotesAI_Setup.exe

#define AppName      "Meeting Notes AI"
#define AppVersion   "1.0.0"
#define AppPublisher "AI Note Taker"
#define AppURL       "https://github.com/adhikari10/AI_Meeting_Notes"
#define AppExeName   "MeetingNotesAI.exe"
#define SourceDir    "dist\MeetingNotesAI"

[Setup]
AppId={{F3A2B8C4-91D7-4E5A-B3F6-2C8D0E1A4B7F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=Output
OutputBaseFilename=MeetingNotesAI_Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763

; Uninstaller
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Copy the entire one-folder bundle
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; App icon (for shortcuts)
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Offer to launch the app after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove user-generated data only if the user explicitly wants to
; (notes & uploads are NOT auto-deleted — user must do this manually)
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
// ── Optional: prevent running multiple instances during install ──────────────
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
