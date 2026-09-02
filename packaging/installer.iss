; Inno Setup script — builds MeeradaSetup.exe, a normal Windows installer.
; Installs a PyInstaller --onedir build to the user's local Programs folder (no
; admin needed), adds Start-menu + optional Desktop shortcuts, and an uninstaller.
; Paths are relative to the repo root (SourceDir=..), so run ISCC on this file
; after `pyinstaller ... --onedir` has produced dist\Meerada\.

#define AppName "Meerada LLManager"
#define AppVersion "0.1.0"
#define AppExe "Meerada.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Meerada
DefaultDirName={autopf}\Meerada
DefaultGroupName=Meerada
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
SourceDir=..
OutputDir=installer
OutputBaseFilename=MeeradaSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\Meerada\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
