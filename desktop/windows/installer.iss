; Inno Setup script: per-user Windows installer for the desktop app.
; Compiled in CI after PyInstaller has produced dist\MarineDocIntelligence\ and
; Tesseract has been copied into it. Produces dist\MarineDocIntelligence-Setup.exe.
;
;   ISCC.exe desktop\windows\installer.iss [/DAppVersion=0.1.0]

#ifndef AppVersion
  #define AppVersion "0.2.2"
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
; The app's window is a Microsoft WebView2 view. Nearly every Windows 10/11
; machine already has the runtime; on one that does not, the app can only open
; in a browser tab. CI downloads this bootstrapper next to the script; it is
; run only when the runtime is missing (see [Code]).
Source: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

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

[Code]
// Is the Evergreen WebView2 runtime present? Microsoft's documented check:
// a "pv" version value under the EdgeUpdate client key, per machine or per user.
function WebView2Installed(): Boolean;
var
  pv: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', pv)
         or RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', pv);
  Result := Result and (pv <> '') and (pv <> '0.0.0.0');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssPostInstall) and (not WebView2Installed()) then
  begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('The Microsoft WebView2 runtime could not be installed (code ' + IntToStr(ResultCode) + '), ' +
             'usually because there is no Internet connection right now. The app still works: it will open in your web browser ' +
             'instead of its own window until the runtime is installed.', mbInformation, MB_OK);
  end;
end;
