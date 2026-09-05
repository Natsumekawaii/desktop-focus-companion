#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir "..\dist\installer"
#endif

#define MyAppName "Desktop Focus Companion"
#define MyAppExeName "DesktopFocusCompanion.exe"
#ifndef MyAppMutexName
  #define MyAppMutexName "DesktopFocusCompanion-31BF15A5-C9F6-4850-B158-CEB3C598956C"
#endif
#ifndef MyAppId
  #define MyAppId "31BF15A5-C9F6-4850-B158-CEB3C598956C"
#endif
#ifndef InstallerOutputBaseFilename
  #define InstallerOutputBaseFilename "DesktopFocusCompanion-Setup-" + MyAppVersion
#endif

[Setup]
AppId={{{#MyAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={localappdata}\Programs\DesktopFocusCompanion
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex={#MyAppMutexName}
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile={#ProjectRoot}\assets\icons\desktop-focus-companion.ico
OutputDir={#InstallerOutputDir}
OutputBaseFilename={#InstallerOutputBaseFilename}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#ProjectRoot}\installer\languages\ChineseSimplified.isl"

[Messages]
english.SetupAppRunningError=Setup detected that %1 is still running.%n%nChoose Exit from the companion's tray-icon menu; closing a window alone does not exit it. Then click OK to continue, or Cancel to exit Setup.
english.UninstallAppRunningError=Uninstall detected that %1 is still running.%n%nChoose Exit from the companion's tray-icon menu; closing a window alone does not exit it. Then click OK to continue, or Cancel to exit Uninstall.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\DesktopFocusCompanion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Dirs]
Name: "{app}"; Flags: uninsalwaysuninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
const
  StartupKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  StartupValueName = 'Desktop Focus Companion';

var
  MigrateStartupEntry: Boolean;

function UnquoteCommand(const Value: String): String;
begin
  Result := Value;
  if (Length(Result) >= 2) and (Result[1] = '"') and
     (Result[Length(Result)] = '"') then
  begin
    Result := Copy(Result, 2, Length(Result) - 2);
  end;
end;

function InitializeSetup(): Boolean;
var
  ExistingCommand: String;
begin
  MigrateStartupEntry :=
    (CompareText(ExpandConstant('{param:NoStartupMigration|0}'), '1') <> 0) and
    RegQueryStringValue(HKCU, StartupKey, StartupValueName, ExistingCommand);
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and MigrateStartupEntry then
  begin
    RegWriteStringValue(
      HKCU,
      StartupKey,
      StartupValueName,
      '"' + ExpandConstant('{app}\{#MyAppExeName}') + '"'
    );
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RegisteredCommand: String;
  InstalledExecutable: String;
begin
  if CurUninstallStep <> usUninstall then
  begin
    Exit;
  end;

  InstalledExecutable := ExpandConstant('{app}\{#MyAppExeName}');
  if RegQueryStringValue(
       HKCU, StartupKey, StartupValueName, RegisteredCommand
     ) and
     (CompareText(UnquoteCommand(RegisteredCommand), InstalledExecutable) = 0) then
  begin
    RegDeleteValue(HKCU, StartupKey, StartupValueName);
  end;
end;
