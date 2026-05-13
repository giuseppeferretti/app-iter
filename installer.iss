; Inno Setup script para gerar o instalador do App Iter.
;
; Como rodar (de c:\dev\app_anac):
;   1. Rodar `pyinstaller build.spec` primeiro (gera dist\AppIter\).
;   2. & "C:\Users\giuseppe\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
;   3. Gera: Output\AppIter_Setup.exe

#define MyAppName "App Iter"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Iter"
#define MyAppURL "https://app-anac.vercel.app"
#define MyAppExeName "AppIter.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-4789-ABCD-1234567890AB}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/suporte
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Iter\AppIter
DefaultGroupName=Iter\App Iter
DisableProgramGroupPage=yes
OutputBaseFilename=AppIter_Setup
SetupIconFile=app\assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AppIter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".env.dist"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
