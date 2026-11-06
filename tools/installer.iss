; Inno Setup 6 script. Built by tools\build.ps1.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C3A52-7B1E-4B0C-9C55-3E0D2A7B8C11}
AppName=VidCompare
AppVersion={#AppVersion}
AppPublisher=Pierre
DefaultDirName={autopf}\VidCompare
DefaultGroupName=VidCompare
OutputDir={#OutDir}
OutputBaseFilename=VidCompare-Setup
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\VidCompare.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "ffmpeg"; Description: "Install FFmpeg (needed to read videos) with winget"; Check: NeedFFmpeg
Name: "webview2"; Description: "Install Microsoft WebView2 (needed to show the window) with winget"; Check: NeedWebView2

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\VidCompare"; Filename: "{app}\VidCompare.exe"
Name: "{autodesktop}\VidCompare"; Filename: "{app}\VidCompare.exe"; Tasks: desktopicon

[Run]
Filename: "winget"; Parameters: "install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements"; Flags: runhidden waituntilterminated; Tasks: ffmpeg; StatusMsg: "Installing FFmpeg..."
Filename: "winget"; Parameters: "install --id Microsoft.EdgeWebView2Runtime -e --accept-package-agreements --accept-source-agreements"; Flags: runhidden waituntilterminated; Tasks: webview2; StatusMsg: "Installing WebView2..."
Filename: "{app}\VidCompare.exe"; Description: "{cm:LaunchProgram,VidCompare}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedFFmpeg: Boolean;
var Rc: Integer;
begin
  Result := not Exec(ExpandConstant('{cmd}'), '/C where ffprobe', '', SW_HIDE, ewWaitUntilTerminated, Rc) or (Rc <> 0);
end;

function NeedWebView2: Boolean;
var V: String;
begin
  Result := not (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V)
    or RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', V));
end;
