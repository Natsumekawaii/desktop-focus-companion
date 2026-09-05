# Verification Guide

This document records reproducible release checks. It intentionally contains no machine-specific paths, personal data, one-off timestamps, or stale artifact hashes.

## 1. Quality gate

Create a Python 3.12 virtual environment, install the development dependencies, and run:

```powershell
.\quality.ps1
```

The command must complete all three gates without modifying tracked files:

1. `ruff check .`
2. `mypy app main.py`
3. `pytest -q`

Coverage includes persistence, schema migration, Focus Items and Sessions, recovery, analytics, responsive Qt widgets, themes, localization, tooltips, page transitions, Windows integration, packaging, and installer behavior.

## 2. README screenshots

Screenshots must be generated from isolated synthetic profiles, never from a real user database:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_readme_screenshots --language zh-CN
.\.venv\Scripts\python.exe -m scripts.capture_readme_screenshots --language en-US
```

Verify that every image referenced by `README.md` exists, uses the intended language, contains no personal data, and renders legibly on GitHub.

## 3. Portable application

Install the build dependencies and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

The build is accepted only when:

- `dist\DesktopFocusCompanion\DesktopFocusCompanion.exe` exists;
- the packaged-runtime smoke test exits successfully against an isolated profile;
- Qt platform and image plugins, translations, icons, and the bundled companion image are present;
- neither `build\` nor `dist\` contains a user database or settings file.

## 4. Windows installer

With Inno Setup 6 available, run:

```powershell
.\build-installer.ps1
```

If the compiler is missing, dependency installation must be an explicit choice:

```powershell
.\build-installer.ps1 -InstallDependencies
```

The installer smoke test must verify:

- a running application mutex blocks install or uninstall with a clear exit instruction;
- a lower-version installation upgrades in place;
- reinstalling the current version does not create a duplicate application;
- obsolete program files are replaced;
- installed application startup succeeds;
- uninstall removes program files and shortcuts while preserving the isolated user-data marker;
- the Windows pending-file-operation queue is unchanged by the test.

## 5. Release artifacts

For a version `X.Y.Z`, the release workflow must produce:

```text
DesktopFocusCompanion-Setup-X.Y.Z.exe
DesktopFocusCompanion-Portable-X.Y.Z.zip
SHA256SUMS.txt
```

Confirm that the Git tag is `vX.Y.Z`, `app.__version__` is `X.Y.Z`, and the installer metadata uses the same version. Download each uploaded asset from the published GitHub Release and verify its SHA-256 against `SHA256SUMS.txt` before announcing the release.

## 6. Manual release smoke test

On a clean Windows test profile:

1. Install without administrator privileges.
2. Launch from the Start menu and verify the tray icon and desktop companion.
3. Open Focus controls, Dashboard, Settings, and Focus Item management.
4. Switch language and each of the six themes.
5. Complete one Stopwatch and one Countdown session.
6. Restart and confirm that settings and history persist.
7. Uninstall and confirm that the program directory is removed while the user-data directory remains.

Unsigned releases may trigger Windows SmartScreen. This is expected until the project adopts a trusted code-signing certificate.
