; Inno Setup script: per-user Windows installer for the desktop app.
; Compiled in CI after PyInstaller has produced dist\MarineDocIntelligence\ and
; Tesseract has been copied into it. Produces dist\MarineDocIntelligence-Setup.exe.
;
;   ISCC.exe desktop\windows\installer.iss [/DAppVersion=0.1.0]

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Marine Electrical Document Intelligence"
#define AppExe "MarineDocIntelligence.exe"
#define Publisher "rampage2gene"

[Setup]
AppId={{7C2F5D1E-6B0A-4E7B-9C7D-3A1F0E5B2D41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL=https://github.com/rampage2gene/new
; Per-user install: no administrator prompt, lands in %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MarineDocIntelligence
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=MarineDocIntelligence-Setup
SetupIconFile=..\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\dist\MarineDocIntelligence\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app writes nothing under {app}; user data stays in
; %LOCALAPPDATA%\Marine Electrical Document Intelligence and is kept on uninstall.
Type: filesandordirs; Name: "{app}\_internal"
