# Design: Phase 10A.3 — Installer 64-Bit Architecture Mode (#815)

## Overview & Goals

Phase 10A.3 (#815) configures the Windows installer (`installer/cbpos.iss`) for 64-bit execution and defines the distribution stance for the initial public release:
1. **64-bit Installation Target**: The CB POS executable is built with 64-bit Python (`pyinstaller cbpos.spec`). However, Inno Setup historically ran in 32-bit setup mode by default, causing `{autopf}` to resolve to `C:\Program Files (x86)` on 64-bit Windows. Phase 10A.3 configures `ArchitecturesAllowed=x64compatible` and `ArchitecturesInstallIn64BitMode=x64compatible` so fresh installs target `C:\Program Files\CB POS`.
2. **Safe Upgrade Path (Bridging 32-to-64-Bit Registry)**: Existing pre-release installations (e.g. 1.3.0) reside under `C:\Program Files (x86)\CB POS`, registered in the 32-bit registry hive (`HKLM32` / `WOW6432Node`). Because a 64-bit Inno Setup process normally checks only `HKLM64` for `UsePreviousAppDir`, a custom Pascal script `GetInstallDir` inspects `HKLM32` first. If a legacy 32-bit installation exists, its directory is honored and preserved in place. During `ssPostInstall`, the legacy 32-bit uninstaller registry key is cleaned up to prevent duplicate entries in Windows "Installed Apps".
3. **Data Safety**: All mutable user data (SQLite database `cbpos.db`, secrets `.encryption_key`, settings `config.json`, logs, backups) resides in `%LOCALAPPDATA%\CB POS`. The installer never touches, overwrites, or deletes files in `%LOCALAPPDATA%\CB POS`. Neither `[InstallDelete]` nor `[UninstallDelete]` may ever target `{localappdata}`. Upgrades and uninstalls leave shop data completely intact.
4. **Code Signing Stance (Locked Decisions D7 & D33)**: First public release remains unsigned. Users are provided clear, step-by-step SmartScreen bypass instructions ("More info" -> "Run anyway") in `public-releases-readme.md`. Paid code signing (e.g., Azure Trusted Signing or OV/EV cert) is tracked in a dedicated GitHub follow-up issue once an organizational entity and signing budget exist.
5. **No Portable ZIP (Locked Decision D33)**: Portable ZIP builds are deliberately rejected for the first public build. Portable installs violate the `%LOCALAPPDATA%` data directory rule and break the automatic update mechanism.

---

## Architecture (Elephant View)

```
[PyInstaller 64-bit Build]
          │
          ▼
   dist/cbpos/cbpos.exe (64-bit binary)
          │
          ▼
[Inno Setup Compiler: installer/cbpos.iss]
  ├── ArchitecturesAllowed=x64compatible
  ├── ArchitecturesInstallIn64BitMode=x64compatible
  ├── UsePreviousAppDir=yes
  ├── MinVersion=10.0
  ├── DefaultDirName={code:GetInstallDir}
  └── [Code] GetInstallDir & CurStepChanged cleanup
          │
          ├───────────────────────────────────────────────┐
          ▼                                               ▼
[Fresh Install on 64-bit Windows]               [Upgrade from 1.3.0 x86 Path]
  - No existing AppId in HKLM32 or HKLM64        - HKLM32 uninstall key found
  - GetInstallDir returns `{autopf}\CB POS`      - GetInstallDir returns
  - Installs to `C:\Program Files\CB POS`          `C:\Program Files (x86)\CB POS`
  - Creates 64-bit uninstaller in HKLM64         - Installs over 1.3.0 in-place
  - Shortcuts point to 64-bit location           - ssPostInstall cleans up HKLM32 key
          │                                               │
          └───────────────────────┬───────────────────────┘
                                  ▼
                     [%LOCALAPPDATA%\CB POS]
                      - Unchanged & untouched
                      - cbpos.db, config.json, logs
```

---

## Detailed Specifications (Goldfish Invariants)

### Invariant 1: Inno Setup 64-Bit Directives
In `installer/cbpos.iss`, under `[Setup]`:
```ini
; 64-bit installer mode for Windows 10/11 64-bit (x64 and ARM64 with emulation)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={code:GetInstallDir}
UsePreviousAppDir=yes
```
- `ArchitecturesAllowed=x64compatible`: Blocks installation on 32-bit-only Windows or unsupported architectures.
- `ArchitecturesInstallIn64BitMode=x64compatible`: Causes Inno Setup to operate in 64-bit mode on 64-bit Windows, so `{autopf}` maps to 64-bit `C:\Program Files` instead of `C:\Program Files (x86)`.

### Invariant 2: Upgrade Directory Resolution & Legacy Uninstaller Cleanup
In `installer/cbpos.iss` under `[Code]`:
```pascal
function GetInstallDir(Param: String): String;
var
  PrevDir: String;
begin
  // If upgrading an existing 32-bit install on 64-bit Windows, honor the legacy path
  if RegQueryStringValue(HKLM32, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1', 'Inno Setup: App Path', PrevDir) and (PrevDir <> '') then
    Result := PrevDir
  else
    Result := ExpandConstant('{autopf}\{#MyAppName}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
  LegacyKey: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Ensure user data directory exists
    DataDir := ExpandConstant('{localappdata}\{#MyAppName}');
    if not DirExists(DataDir) then
      ForceDirectories(DataDir);

    // Clean up legacy 32-bit uninstaller registry entry if migrating from 32-bit install
    LegacyKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
    if RegKeyExists(HKLM32, LegacyKey) then
      RegDeleteKeyIncludingSubkeys(HKLM32, LegacyKey);
  end;
end;
```
- When upgrading from a 32-bit install, `GetInstallDir` detects the path from `HKLM32` and keeps the app in `C:\Program Files (x86)\CB POS`.
- When upgrading from a previous 64-bit install, native `UsePreviousAppDir=yes` reads `HKLM64` automatically.
- During `ssPostInstall`, the legacy `HKLM32` uninstaller key is deleted so only the single new 64-bit uninstaller entry in `HKLM64` exists in Windows Apps & Features.

### Invariant 3: System Requirements & Minimum Version
- `MinVersion=10.0` is enforced (Windows 10 / Windows Server 2016 or later).
- Verified `public-releases-readme.md`: Line 119 already requires "Windows 10 (64-bit) or later".

### Invariant 4: Unsigned Binaries & SmartScreen Instructions
- Verified `public-releases-readme.md`: Lines 132–133 already state:
  ```markdown
  > **Windows SmartScreen Warning:** Since CB POS is new software, Windows may show a "Windows protected your PC" message. Click **"More info"** then **"Run anyway"**. This is normal for new applications and will go away as the software gains more users.
  ```
- No SignTool step is added to `.github/workflows/release.yml` at this time (per D7 and D33).
- A follow-up GitHub issue will track Azure Trusted Signing setup once corporate/identity verification is complete.

### Invariant 5: Guardrail Tests in `tests/guardrails/test_installer_config.py`
Add dedicated tests in `tests/guardrails/test_installer_config.py` asserting:
1. `ArchitecturesAllowed=x64compatible` is specified in `installer/cbpos.iss`.
2. `ArchitecturesInstallIn64BitMode=x64compatible` is specified in `installer/cbpos.iss`.
3. `UsePreviousAppDir=yes` is specified in `installer/cbpos.iss`.
4. `MinVersion=10.0` is specified in `installer/cbpos.iss`.
5. `DefaultDirName={code:GetInstallDir}` is specified in `installer/cbpos.iss`, and `GetInstallDir` falls back to `{autopf}\{#MyAppName}`.
6. `PrivilegesRequired=admin` is specified in `installer/cbpos.iss`.
7. `CheckForMutexes('CBPOSAppMutex')` is checked in `InitializeSetup`.
8. User data safety: verify `{localappdata}` never appears in `[UninstallDelete]` or `[InstallDelete]`.

### Invariant 6: Manual Verification on Windows VM (`⚠️ Verify on Windows`)
- Checklist:
  1. Clean install on 64-bit Windows VM -> installs under `C:\Program Files\CB POS`.
  2. Upgrade test on 64-bit Windows VM with pre-existing 1.3.0 in `C:\Program Files (x86)\CB POS` -> upgrades cleanly in place in `C:\Program Files (x86)\CB POS`, single uninstaller entry in Apps & Features, shortcuts function, data in `%LOCALAPPDATA%\CB POS` intact.
  3. Uninstallation test on Windows VM: Run uninstaller -> removes `{app}` binaries, leaves `%LOCALAPPDATA%\CB POS` (`cbpos.db`, `.encryption_key`, `config.json`, logs) completely intact.
