; Dan Windows Installer — Inno Setup 6.x script
;
; Prerequisites
; -------------
; 1. Build the PyInstaller bundle first:
;       python scripts\build_windows.py --target gui
;    This produces:  dist\windows\Dan\Dan.exe  (and supporting files)
;
; 2. (Optional) Build the CLI companion:
;       python scripts\build_windows.py --target cli
;    This produces:  dist\windows\DanCLI\DanCLI.exe
;
; 3. Compile this script with Inno Setup 6.x:
;       iscc installer\Dan.iss
;    Or open it in the Inno Setup IDE and click Build > Compile.
;
; Download Inno Setup: https://jrsoftware.org/isdl.php
;
; Output
; ------
; dist\installer\Dan-<version>-setup.exe
;
; The installer is a portable, per-user install by default (no admin rights
; required).  Users can opt in to a system-wide install during setup.
; A Desktop shortcut and CLI PATH registration are offered as optional tasks.

; ── Version constants ────────────────────────────────────────────────────────
; Keep AppVersion in sync with pyproject.toml [project] version.
#define MyAppName      "Dan"
#define MyAppVersion   "2.5.1"
#define MyAppPublisher "Dan Project"
#define MyAppURL       "https://github.com/your-org/dan"
#define MyAppExeName   "Dan.exe"
#define MyCliExeName   "DanCLI.exe"

; ── Source directories (relative to this script's location) ─────────────────
#define GuiDistDir  "..\dist\windows\Dan"
#define CliDistDir  "..\dist\windows\DanCLI"

; ── Build output ─────────────────────────────────────────────────────────────
#define OutputDir    "..\dist\installer"
#define OutputName   "Dan-" + MyAppVersion + "-setup"

; ── A stable GUID for the AppId — generate once, never change ───────────────
; This lets Windows identify upgrades vs. fresh installs correctly.
; If you fork Dan, generate a new GUID with: powershell -command "[guid]::NewGuid()"
#define AppGUID "{6F3A2B7E-D4C8-4A91-B5F0-2E8D1C4F9A30}"

[Setup]
AppId={#AppGUID}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Per-user install by default so no admin rights are needed.
; Change to admin if you want a machine-wide install.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Output
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}

; Compression — lzma gives ~40 % smaller installers at the cost of slower build.
Compression=lzma
SolidCompression=yes

; Visual style
WizardStyle=modern
SetupIconFile=..\assets\dan_icon.ico
; ^ If dan_icon.ico doesn't exist yet, comment this line out or create the asset.

; Minimum Windows version: Windows 10 (build 10240)
MinVersion=10.0.10240

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Optional tasks offered to the user ──────────────────────────────────────
[Tasks]
Name: "desktopicon"; \
    Description: "Create a &Desktop shortcut"; \
    GroupDescription: "Additional icons:"; \
    Flags: unchecked

Name: "addclitopath"; \
    Description: "Add DanCLI to the user PATH (enables 'dan' command in any terminal)"; \
    GroupDescription: "Developer options:"; \
    Flags: unchecked; \
    Check: CliDistDirExists

; ── Files to install ─────────────────────────────────────────────────────────
[Files]
; GUI bundle — always installed
Source: "{#GuiDistDir}\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; CLI companion — installed only when the dist directory exists
Source: "{#CliDistDir}\*"; \
    DestDir: "{app}\cli"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Check: CliDistDirExists

; ── Shortcuts ────────────────────────────────────────────────────────────────
[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"

Name: "{group}\Uninstall {#MyAppName}"; \
    Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}"; \
    Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

; ── Registry — PATH for CLI ──────────────────────────────────────────────────
[Registry]
; Append {app}\cli to the user PATH when the addclitopath task is selected.
; Uses expandsz so %LOCALAPPDATA% survives profile moves.
Root: HKCU; \
    Subkey: "Environment"; \
    ValueType: expandsz; \
    ValueName: "Path"; \
    ValueData: "{app}\cli;{olddata}"; \
    Tasks: addclitopath; \
    Check: CliDistDirExists

; ── Post-install launch ───────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

; ── Pascal helper functions ──────────────────────────────────────────────────
[Code]
{ Returns True when the CLI dist directory was included in the build. }
function CliDistDirExists: Boolean;
begin
  Result := DirExists(ExpandConstant('{src}\..\dist\windows\DanCLI'));
end;
