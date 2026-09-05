"""Static contracts for the Windows installer and its build pipeline."""

from pathlib import Path

from app import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DEFINITION = PROJECT_ROOT / "installer" / "DesktopFocusCompanion.iss"
INSTALLER_BUILD = PROJECT_ROOT / "build-installer.ps1"


def _installer_text() -> str:
    return INSTALLER_DEFINITION.read_text(encoding="utf-8")


def test_installer_is_stable_per_user_and_preserves_application_data() -> None:
    text = _installer_text()

    assert '#define MyAppId "31BF15A5-C9F6-4850-B158-CEB3C598956C"' in text
    assert "#ifndef MyAppId" in text
    assert "AppId={{{#MyAppId}}" in text
    assert "DefaultDirName={localappdata}\\Programs\\DesktopFocusCompanion" in text
    assert "PrivilegesRequired=lowest" in text
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in text
    assert "[UninstallDelete]" not in text
    assert "desktop-focus-companion.sqlite3" not in text


def test_installer_blocks_running_app_without_forcing_a_restart() -> None:
    text = _installer_text()

    assert (
        '#define MyAppMutexName "DesktopFocusCompanion-31BF15A5-C9F6-4850-B158-CEB3C598956C"'
        in text
    )
    assert "#ifndef MyAppMutexName" in text
    assert "AppMutex={#MyAppMutexName}" in text
    assert "CloseApplications=yes" in text
    assert "CloseApplications=force" not in text
    assert "closing a window alone does not exit it" in text

    chinese_messages = (
        PROJECT_ROOT / "installer" / "languages" / "ChineseSimplified.isl"
    ).read_text(encoding="utf-8")
    assert "仅关闭窗口不会退出桌宠" in chinese_messages


def test_installer_has_standard_shortcuts_and_optional_desktop_icon() -> None:
    text = _installer_text()

    assert 'Name: "desktopicon"' in text
    assert "Flags: unchecked" in text
    assert 'Name: "{autoprograms}\\{#MyAppName}"' in text
    assert 'Name: "{autodesktop}\\{#MyAppName}"' in text
    assert "Tasks: desktopicon" in text
    assert "nowait postinstall skipifsilent" in text


def test_installer_packages_the_complete_portable_distribution() -> None:
    text = _installer_text()

    assert (
        'Source: "{#ProjectRoot}\\dist\\DesktopFocusCompanion\\*"' in text
    )
    assert "Flags: ignoreversion recursesubdirs createallsubdirs" in text
    assert '[InstallDelete]\nType: filesandordirs; Name: "{app}\\*"' in text
    assert '[Dirs]\nName: "{app}"; Flags: uninsalwaysuninstall' in text
    assert (
        '#define InstallerOutputBaseFilename "DesktopFocusCompanion-Setup-" + MyAppVersion'
        in text
    )
    assert "OutputBaseFilename={#InstallerOutputBaseFilename}" in text
    assert "SetupIconFile={#ProjectRoot}\\assets\\icons\\desktop-focus-companion.ico" in text
    assert (
        'MessagesFile: "{#ProjectRoot}\\installer\\languages\\ChineseSimplified.isl"'
        in text
    )


def test_installer_migrates_and_safely_removes_its_startup_entry() -> None:
    text = _installer_text()

    assert "{param:NoStartupMigration|0}" in text
    assert "RegQueryStringValue(HKCU, StartupKey, StartupValueName" in text
    assert "if (CurStep = ssPostInstall) and MigrateStartupEntry" in text
    assert "CompareText(UnquoteCommand(RegisteredCommand), InstalledExecutable)" in text
    assert "RegDeleteValue(HKCU, StartupKey, StartupValueName)" in text


def test_installer_build_uses_canonical_version_and_runs_smoke_checks() -> None:
    text = INSTALLER_BUILD.read_text(encoding="utf-8")

    assert "from app import __version__; print(__version__)" in text
    assert "& $applicationBuildScript" in text
    assert "JRSoftware.InnoSetup" in text
    assert (
        "Installer mutex/install/upgrade/reinstall/start/uninstall/reboot-queue smoke test passed."
        in text
    )
    assert "installer-data-preservation.marker" in text
    assert "'/NoStartupMigration=1'" in text
    assert "[System.Guid]::NewGuid()" in text
    assert '"/DMyAppId=$smokeAppId"' in text
    assert "$smokeSetupPath" in text
    assert "$smokeBaselineVersion = '0.9.9'" in text
    assert "Silent version upgrade" in text
    assert "Silent same-version reinstall" in text
    assert "obsolete-build.marker" in text
    assert "Get-PendingFileRenameOperations" in text
    assert "$pendingOperationsBefore" in text
    assert "$pendingOperationsAfter" in text
    assert "A build must not create a reboot requirement." in text
    assert '"/DMyAppMutexName=$smokeMutexName"' in text
    assert "$smokeMutexName" in text
    assert "Installer was not blocked by the running-application mutex." in text
    assert "DesktopFocusCompanion-Setup-$appVersion.exe" in text
    assert __version__ == "1.0.0"
