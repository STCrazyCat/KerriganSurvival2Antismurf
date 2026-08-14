; AntiSmurf Windows installer (Inno Setup 6)
; Build: scripts\build_installer.ps1

#define AppName "AntiSmurf"
#define AppPublisher "AntiSmurf"
#ifndef AppURL
  #define AppURL "https://github.com/STCrazyCat/KerriganSurvival2Antismurf"
#endif
#define AppExeName "AntiSmurf.exe"

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef AppVersionNumeric
  #define AppVersionNumeric "1.0.0.0"
#endif

[Setup]
AppId={{B8C4D2E1-5F3A-6B7C-9D0E-2F3A4B5C6D7E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\AntiSmurf
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AntiSmurf-Setup-{#AppVersion}
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
VersionInfoVersion={#AppVersionNumeric}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersionNumeric}

[Languages]
; 简体中文语言包需单独下载：https://jrsoftware.org/files/istrans/
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\community_stub.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
Source: "..\config\user.toml.example"; DestDir: "{app}\config"; DestName: "user.toml.example"; Flags: ignoreversion
Source: "..\config\blocklist.txt"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
Source: "..\config\COMMUNITY_API.md"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "使用说明.txt"; Flags: ignoreversion isreadme

[Dirs]
Name: "{app}\config"; Permissions: users-modify
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
