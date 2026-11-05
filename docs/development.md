[English](development.md) | [简体中文](development.zh-CN.md)

# Local development

## Optional DeepSeek assistant

This branch adds an **unpublished** AI Assistant page after the six existing Focus Center pages. Run `dev.ps1`, open Focus Center → AI Assistant → AI configuration. Enter a personal Key locally, read the disclosure, and choose Verify and save. The official model list must contain the selected model (`deepseek-flash` by default, optionally `deepseek-v4-pro`). Deep thinking is explicit; unavailable models are never silently replaced. No Key is bundled and no paid request is part of automated testing.

Chats and settings live under `.dev-data/agent`; Windows credentials are namespaced to that profile. Never send the Key to a developer, paste it in chat, put it in environment files for this feature, or include it in screenshots. With the Key removed or AI disabled, other features remain offline. See [Data safety](data-safety.md#optional-ai-and-data-leaving-the-device).

```powershell
.\quality.ps1 -Mode Fast -Tests tests/test_agent.py,tests/test_agent_write_reliability.py
```

Tests inject a fake network client and temporary databases. They exercise SSE, tool authorization, paging beyond 1,000 records, DST, confirmation/cancellation, atomic rollback, receipts, profile isolation and bilingual themed widgets. The deterministic capture helper in `scripts/capture_ui_baseline.py` also includes the appended page. Do not replace mock tests with live API tests in CI.

For a separately agreed live check, use only newly seeded synthetic records in an isolated development profile. The default budget is **six completion requests** unless the user explicitly agrees to a different cumulative cap; model-list verification is separate. Count actual requests, including tool continuations and cancellations, across resumed runs. Stop at the cap or the first reproducible failure. Suggested cases: a factual query with sources; an incomplete request followed by date/time/project details; and a confirmed note edit. A turn also has a hard eight-request ceiling. Stop prevents new calls but cannot refund sent requests or undo committed records.

Write authorization is client-owned and separate from field evidence. An unfinished request can accept follow-up details without the user repeating the command or the assistant ending its question with a question mark. A new topic, cancellation, session switch or restart ends that permission. “Only change the note” locks all other fields; requesting batch confirmation cannot be reduced to automatic single-record writes.

The v2 tool contract references a client request ID and exact fragments from indexed user messages. Date and time may come from separate messages. Updates contain only changed fields; deletes contain only the operation kind and previously read record ID. Before a valid plan exists, one format-only correction may repair evidence structure or redundant delete fields, never targets, counts or field values. Missing facts and duration conflicts require user clarification, not retries. Tool cards normally show only the operation name and status. Pending confirmations expand to show the complete batch, readable before/after changes, overlaps and action buttons. Record times remain available for review; query timestamps and raw JSON are never displayed. Completed/cancelled cards collapse again, and failures expose a localized explanation through the header tooltip. Internal evidence and stored results are unchanged.

Natural-language grounding is deliberately conservative. If a date/time phrase is not recognized, the assistant asks for an explicit date and HH:MM; it must not guess. Project IDs must resolve to existing user-chosen items. Long histories stay local, while only complete recent turns fit into the bounded request context. Chat notes can contain private information even when the API Key is securely stored.

## Quick loop

The AI composer places the model and thinking controls beside one Send/Stop button below the input. While a cancelled local tool is finishing, the same button shows disabled “Stopping…”; drafts and committed focus records are retained. Right-click a conversation (or use the Menu key / Shift+F10) to rename or delete that specific chat without activating it. Manual names are persisted in the existing chat key/value store and survive first-message auto-titling. Deleting the active chat stops its turn and waits asynchronously for owned tool callbacks before removing history; deleting another chat leaves the current response alone. Rename/delete failures never trigger an automatic model request.

The Focus Center sidebar has a top toggle: expanded navigation is 160px wide and the icon-only rail is 52px. Live layout resizing takes up to 180ms (OutCubic); labels and group heights transition with it, and repeated clicks reverse from the current frame without queuing. Before the first manual choice, windows below 900px use the rail automatically. A manual choice takes precedence at every width and is saved per profile as `dashboard_sidebar_mode` (`auto`, `expanded`, or `collapsed`). Toggling does not switch pages, reload data, clear drafts, or interrupt AI responses. If saving fails, the previous layout is restored and the Focus Center shows an error. Changes to this source UI appear after exiting and restarting the development app; existing packaged builds are not updated automatically.

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
