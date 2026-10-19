; Optional Inno Setup 6 installer. Run after the Windows PyInstaller build.
#define MyAppVersion "1.0.0"
[Setup]
AppId={{DF6D1579-64E2-451A-847B-5A1B81DE87B1}
AppName=Finance Ledger
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\FinanceLedger
DefaultGroupName=Finance Ledger
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=FinanceLedger-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\FinanceLedger.exe
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\FinanceLedger\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Finance Ledger"; Filename: "{app}\FinanceLedger.exe"
Name: "{autodesktop}\Finance Ledger"; Filename: "{app}\FinanceLedger.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\FinanceLedger.exe"; Description: "Launch Finance Ledger"; Flags: nowait postinstall skipifsilent
; No UninstallDelete section: the separate data directory and backups are preserved.
