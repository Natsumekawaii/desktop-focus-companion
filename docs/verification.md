[English](verification.md) | [简体中文](verification.zh-CN.md)

# Verification Guide

This document records reproducible release checks. It intentionally contains no machine-specific paths, personal data, one-off timestamps, or stale artifact hashes.

## 1. Quality gate

Create a Python 3.12.10 virtual environment, install the development dependencies, and run:

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

Verify that every image referenced by `README.md` or `README.zh-CN.md` exists, uses the intended language, contains no personal data, and renders legibly on GitHub.

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
- distribution files contain no production database or settings; isolated smoke-test profiles and diagnostics may remain under `build\`.

## 4. Windows installer

With Inno Setup 6.7.3 available, run:

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
- no new application/test paths appear in the paired Windows pending-file-operation queue; unrelated software changes produce a warning, and the queue is never edited.

## 5. Release artifacts

For a version `X.Y.Z`, the release workflow must produce:

```text
DesktopFocusCompanion-Setup-X.Y.Z.exe
DesktopFocusCompanion-Portable-X.Y.Z.zip
SHA256SUMS.txt
```

Confirm that the Git tag is `vX.Y.Z`, `app.__version__` is `X.Y.Z`, and the installer metadata uses the same version. Download each uploaded asset from the published GitHub Release and verify its SHA-256 against `SHA256SUMS.txt` before announcing the release.

Release notes must exist as the English default `.github/release-notes/vX.Y.Z.md` and the Simplified Chinese `.github/release-notes/vX.Y.Z.zh-CN.md`. The published Release body uses English by default and links to the Chinese document at the tagged commit.

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
## 7. Development hardening gates

See [Local development](development.md) for commands and reports. Verify lossless note/project-only edits, independent start/end/effective duration, 30-hour records, preserved seconds and timer metadata. Exercise malformed/legacy recovery, atomic validation, unavailable storage/logging/locks, IANA timezone changes, DST gaps/folds and 23/25-hour days. The session-level QApplication must return to its test-owned resource baseline after every test.

Run the statistics benchmark at 1,000/10,000/50,000 synthetic records. Each project-metrics/progress snapshot uses one complete read; full Dashboard refresh retains one complete read plus its bounded activity query. Compare before/after screenshots and QSS for both languages, six themes and supported widths. Inspect the edit dialog separately, because its explicit end date and independent duration are intentional changes.

Before building, verify the canonical version, both release-note languages, pinned dependencies, Python and Inno Setup. Test stale/tampered payload rejection, identical existing Release no-op, differing asset rejection, process timeout and source/target reboot-queue filtering. Local builds carry an unpublished manifest; `-SkipApplicationBuild` is not a way around provenance checks. Required PR CI may be awaited, but running logs and main-branch completion are not prerequisites for finishing local development.
