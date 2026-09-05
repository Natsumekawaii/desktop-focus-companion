# PyInstaller configuration for the Windows onedir distribution.

from pathlib import Path

from app.core.paths import APPLICATION_ICON_RELATIVE_PATH, DEFAULT_PET_RELATIVE_PATH

project_root = Path(SPECPATH).resolve()

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (
            str(project_root / "assets" / DEFAULT_PET_RELATIVE_PATH),
            str(Path("assets") / DEFAULT_PET_RELATIVE_PATH.parent),
        ),
        (str(project_root / "assets" / "icons"), str(Path("assets") / "icons")),
        (str(project_root / "app" / "i18n" / "locales" / "en-US.json"), "app/i18n/locales"),
        (str(project_root / "app" / "i18n" / "locales" / "zh-CN.json"), "app/i18n/locales"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
    optimize=1,
)

# Desktop Focus Companion supports static pet images only; PySide6's hook otherwise
# collects the unused GIF image-format plugin automatically.  Also reject ICU
# DLLs discovered through the build host's PATH: Qt for Windows imports the
# unversioned system ICU API, while third-party ICU builds can use the same DLL
# names with incompatible versioned exports and make the packaged app fail at
# startup.
def should_exclude_binary(entry):
    names = {Path(str(value)).name.lower() for value in entry[:2]}
    return "qgif.dll" in names or any(
        name.endswith(".dll") and name.startswith(("icudt", "icuin", "icuuc"))
        for name in names
    )


analysis.binaries = [
    entry
    for entry in analysis.binaries
    if not should_exclude_binary(entry)
]

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DesktopFocusCompanion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / APPLICATION_ICON_RELATIVE_PATH),
    version=str(project_root / "assets" / "windows-version-info.txt"),
)

distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DesktopFocusCompanion",
)
