[English](development.md) | [简体中文](development.zh-CN.md)

# Local development

## Quick loop

Use Windows and Python **3.12.10**. From the repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\dev.ps1
```

The source launcher seeds synthetic demonstration data once in `.dev-data`, then preserves your development state. The development profile has its own instance lock and Windows mutex; its window titles and tray are marked `[DEV]`. Real Windows startup registration is disabled. An installed production instance can remain running.

After a code change, exit the development app from its tray and rerun `dev.ps1`. You do **not** need to download, package or install anything for normal source testing. There is no hot reload.

```powershell
.\dev.ps1 -ResetDemo
```

Reset is explicit, holds the development lock and only accepts the validated repository-owned development directory. Redirected directories are rejected. It never clears the installed AppData profile, stops a production instance, or removes development data during a normal build.

## Quality checks

```powershell
.\quality.ps1 -Mode Fast
.\quality.ps1 -Mode Fast -Tests tests/test_record_hardening.py,tests/test_recovery_hardening.py
.\quality.ps1 -Mode Docs
.\quality.ps1                         # Full is the default
```

All modes run Ruff and mypy first. Fast selects core persistence, timer, recovery, statistics and engineering tests; Docs selects public documentation contracts; Full runs every test. Explicit test paths override the selected pytest set. Reports, per-stage timing and the slowest 25 tests are saved under `artifacts/quality/`.

Qt tests share one QApplication, but each test owns and disposes its runtime objects, windows, timers and animations. Global theme/language and shared tooltip objects are retained or restored. Prefer deterministic animation timestamps for intermediate-frame assertions; keep a small number of bounded real-time integration checks.

## Profiling and visual comparisons

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_statistics
.\.venv\Scripts\python.exe -m scripts.capture_ui_baseline artifacts/visual-before
# Make the implementation change, without changing the synthetic dataset/date.
.\.venv\Scripts\python.exe -m scripts.capture_ui_baseline artifacts/visual-after
```

The benchmark uses temporary SQLite databases with 1,000, 10,000 and 50,000 records, checks old/new result equivalence and records three-run median timings and query counts. Visual capture covers both languages, all six themes, Dashboard pages, Settings and Focus Panel. Compare PNGs and `qss.json`; do not accept visible changes from structural refactors.

## Local builds, not releases

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-installer.ps1
```

Use Inno Setup **6.7.3**. Missing dependencies are never silently installed; `-InstallDependencies` explicitly opts in. The installer command already clean-builds and smoke-tests the application. Do not run `build.ps1` first unless you specifically want just the portable build.

Local installers use the suffix `-local-validation.exe`. The portable directory contains `build-manifest.json`, marked **UNPUBLISHED local validation**, with the canonical app version, source and payload hashes, Git revision/dirty flag and resolved tool/dependency versions. These are diagnostic records, not a promise of byte-for-byte reproducible builds.

`-SkipApplicationBuild` accepts an existing payload only when its version, source hash and payload hash match. Installation tests use a random identity and isolated data, bounded process waits, and retain diagnostic logs. They never edit Windows' pending reboot queue. Real data and the production installation identity remain unchanged.

Only the separate tag workflow can publish. Existing Release assets are never overwritten: an identical asset set is a no-op, and any missing/different asset causes a failure. Development work does not imply permission to push, tag, merge or release.

The release workflow downloads the pinned compiler from its official release and verifies SHA-256 before installation. If workflow bootstrap fails before publication, its manual dispatch accepts an existing version tag: a repaired workflow can build that exact tagged source without moving the tag. Release-note links use the checked-out source revision, not the workflow's revision.

## CI policy

`Windows quality gate` always runs. Documentation-only changes select Docs; code, dependencies, workflows, builds and unknown diff ranges select Full. The job exposes Ruff, mypy and pytest separately and preserves diagnostics.

Do not continuously poll CI or fetch logs while it is running. Inspect logs after failure. Wait for a required PR gate when necessary, but do not wait for a subsequent main-branch run after a successful merge.

Git must be available on PATH for build provenance. Source development itself does not require a packaging toolchain.
