; ============================================================================
; CB POS - Inno Setup Installer Script
; ============================================================================
; Builds a professional Windows installer for CB POS.
;
; Prerequisites:
;   1. Build the PyInstaller exe first:  pyinstaller cbpos.spec
;   2. The output exe is at:             dist/cbpos.exe
;   3. Run Inno Setup Compiler on this file to produce the installer.
;
; Data safety:
;   - User data (database, settings, logs) lives in %LOCALAPPDATA%\CB POS
;   - This installer ONLY writes to Program Files — never touches user data
;   - Updates install cleanly over the previous version
; ============================================================================

#define MyAppName "CB POS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ceylon Byte"
#define MyAppURL "https://ceybyte.com"
#define MyAppExeName "cbpos.exe"
#define MyAppDescription "Free Point of Sale System for Sri Lankan Retail"

[Setup]
; Unique App ID — NEVER change this after first release (used for upgrades)
AppId={{B7E3F2A1-4D5C-6E8F-9A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; No license page — free software
DisableDirPage=yes
DisableProgramGroupPage=yes
; Installer output settings
OutputDir=..\dist\installer
OutputBaseFilename=CBPOSSetup-{#MyAppVersion}
SetupIconFile=..\cbpos\assets\ico\cbpos_multi.ico
UninstallDisplayIcon={app}\cbpos.exe
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
; Modern installer look
WizardStyle=modern
WizardImageFile=..\cbpos\assets\logo\cover_white.png
WizardSmallImageFile=..\cbpos\assets\ico\cbpos.png
; Require admin for Program Files install
PrivilegesRequired=admin
; Allow upgrading over existing installation
UsePreviousAppDir=yes
; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checked
Name: "startupicon"; Description: "Start {#MyAppName} when Windows starts"; GroupDescription: "Additional shortcuts:"

[Files]
; Main application executable
Source: "..\dist\cbpos.exe"; DestDir: "{app}"; Flags: ignoreversion

; Assets bundled inside the exe by PyInstaller — no extra files needed.
; If you switch to folder mode (--onedir), uncomment below:
; Source: "..\dist\cbpos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

; Startup (optional)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
; Launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up any files created at runtime in the install directory
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// -------------------------------------------------------------------------
// Custom Pascal Script — pre-install and post-install hooks
// -------------------------------------------------------------------------

function InitializeSetup(): Boolean;
begin
  // Check if the app is currently running and ask user to close it
  Result := True;
  if CheckForMutexes('CBPOSAppMutex') then
  begin
    MsgBox('{#MyAppName} is currently running.' + #13#10 +
           'Please close it before continuing the installation.',
           mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Ensure user data directory exists
    DataDir := ExpandConstant('{localappdata}\{#MyAppName}');
    if not DirExists(DataDir) then
      ForceDirectories(DataDir);
  end;
end;
