; Inno Setup Script for C3D Explorer
; Creates a professional Windows Setup Installer with .c3d file association

#define MyAppName "C3D Explorer"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Dr. Mohamadreza Kharazi"
#define MyAppURL "https://biomech-lab.pages.dev"
#define MyAppExeName "C3DExplorer.exe"
#define ProjectDir ".."

[Setup]
AppId={{D3F9B732-C3D1-4E8A-9A25-B7D8C61E8921}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir={#ProjectDir}\dist_installer
OutputBaseFilename=C3D_Explorer_Windows_Setup
SetupIconFile={#ProjectDir}\assets\icons\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate_c3d"; Description: "Associate .c3d motion capture files with C3D Explorer"; GroupDescription: "File Associations:"

[Files]
Source: "{#ProjectDir}\dist\C3DExplorer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Associate .c3d files with C3D Explorer
Root: HKA; Subkey: "Software\Classes\.c3d"; ValueType: string; ValueName: ""; ValueData: "C3DExplorer.File"; Flags: uninsdeletevalue; Tasks: associate_c3d
Root: HKA; Subkey: "Software\Classes\C3DExplorer.File"; ValueType: string; ValueName: ""; ValueData: "C3D Motion Capture File"; Flags: uninsdeletekey; Tasks: associate_c3d
Root: HKA; Subkey: "Software\Classes\C3DExplorer.File\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate_c3d
Root: HKA; Subkey: "Software\Classes\C3DExplorer.File\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate_c3d

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
