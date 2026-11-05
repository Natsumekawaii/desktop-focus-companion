[English](architecture.md) | [简体中文](architecture.zh-CN.md)

# Desktop Focus Companion 1.0 Architecture

## Optional assistant boundaries (development branch)

`DashboardPage.AI_ASSISTANT` is index 6; the first six indices and controllers retain their existing contracts. `AgentPage` only presents conversations, Markdown, status/source cards and confirmations. `AgentController` owns one active turn, request budgets, consent, cancellation and profile-local history. No widget executes database or network commands directly.

`DeepSeekClient` uses asynchronous `QNetworkAccessManager` and a bounded incremental SSE parser. UTF-8 fragments are decoded only after complete events; incomplete tool calls, malformed JSON, invalid termination and redirected hosts cannot execute. Network requests and committed operations are not automatically replayed. `reasoning_content` remains in complete protocol turns for DeepSeek tool continuation, but not in the displayed answer. Only the official HTTPS origin is used; model availability is explicitly verified.

`WriteRequestContext` owns a transient request ID, authorized operation/field/record scope and indexed user messages. It survives only a related clarification, never a stop, conversation switch or restart. v2 tools bind to this ID and verify exact message fragments separately from semantic field evidence; legacy calls still pass their original safety checks. Structured validation errors carry stable codes, field paths and categories. Before a plan exists the controller permits one format correction with an unchanged operation signature; missing information, conflicts and expired confirmations are not retried. `ChangePreview` renders readable before/after fields while keeping raw tool JSON collapsed.

`FocusTools` runs in an owned `QThread`, opens independent database connections and pins one IANA timezone per turn. Queries use validated filters, bounded keyset pages and authoritative local aggregation over all matches, reusing UTC-based midnight allocation. The controller snapshots the live timer on the GUI thread and exposes it read-only. No live Qt timer crosses threads. Existing dashboard refresh signals propagate successful record changes to every statistics surface.

`evidence.py` conservatively grounds changed values in user messages, not record notes. `focus_record_changes.apply_changes` independently enforces atomicity, exact snapshot/timezone validation, explicit confirmation where needed, bounded batches and durable UUID receipts in the existing settings table. A pending plan is never executable after restart. A receipt can repair a chat card after a crash without performing the operation again. The separate `agent/conversations.sqlite3` holds conversations/preferences; no main-schema migration or credential-in-JSON fallback is introduced. See [data safety](data-safety.md#optional-ai-and-data-leaving-the-device).

Desktop Focus Companion is a local-first PySide6 personal focus system. The desktop companion is a presentation and shortcut boundary; it does not encode Focus state, goals, consistency, or analytics.

## Composition Root

`app/application.py` constructs one canonical runtime graph:

```text
Database
  -> FocusItemRepository
  -> FocusSessionRepository
  -> StatisticsService
  -> GamificationService

FocusTimer + ActiveSessionStore
  -> FocusSessionManager
  -> FocusPanelController

PetWindow -> PetController
DashboardWindow -> DashboardController
SettingsDialog -> preference controllers
TrayController -> shared ordinary application menu
```

No live controller depends on `SubjectRepository`, `SessionRepository`, `StudyTimer`, or `SessionManager`. Those APIs remain in explicit schema-compatibility modules and regression tests.

## Focus Domain

`FocusItem` contains stable identity, user name, creation-time color, and timestamps; Favorite/Archive columns remain schema-only compatibility fields. `FocusSession` snapshots the current item name and stores actual start/end, whole-minute duration, `FocusMode`, optional Countdown target, optional Note, internal Timer/Manual source, and timestamps.

`FocusTimer` owns the monotonic `IDLE -> FOCUSING -> PAUSED -> FOCUSING -> IDLE` state machine. Qt timers only refresh presentation and request the Countdown zero check. `FocusSessionManager` coordinates selection, recovery checkpoint, exactly-once Finish, pending retry, and repository persistence.

Manual entries use `ManualFocusEntryService` and the same `FocusSessionRepository`. They therefore enter every analytics, Goal, Consistency, Replay, and distribution path without special aggregation logic.

## UI Boundaries

- `PetWindow` renders only one static PNG/JPG/JPEG/WEBP at the exact scaled image size, maintains aspect ratio, receives click/drag/right-click input, and emits intents without owning or mirroring timer state.
- `FocusPanel` uses an internal `QStackedWidget` to keep Idle selection, Pre-start, and Active layouts stable. Idle renders labeled Daily/Weekly Goal progress and one name-sorted text-only selector with a code-drawn theme-aware chevron. Its transparent rounded popup has a Focus-specific delegate: 36px project rows use saved project colors, the committed row has a soft rounded fill and vector checkmark, keyboard candidates remain distinct, a 9px separator precedes the 40px management action, and popup height is the exact sum of visible rows plus insets. Native item selection painting is never invoked. Idle also provides segmented Stopwatch/Countdown, target and optional Note. Active switches a stable visual slot between a plain second-resolution `HH:MM:SS` Stopwatch and the existing theme-aware Countdown ring, followed by Pause/Resume/Finish.
- `FocusItemDialog` owns no persistence; it emits create(name, color), rename, and delete intents only. Its equal-width aggregate cards are read-only, while the 16-color palette exists only in the compact creation dialog.
- `DashboardWindow` uses a responsive left sidebar grouped into Focus, Insights, and Library. The sidebar drives a single shared `QStackedWidget`; widths below the shared breakpoint collapse navigation to an icon rail while preserving tooltips, accessibility names, keyboard focus, and existing `show_*` compatibility methods.
- Focus Center and Settings page stacks share an `AnimatedPageStack`. A visible page change updates the real stack index immediately, retains the leaving frame in a mouse-transparent overlay, and reveals the live target through a 160ms `OutCubic` fade with a 4px upward settle. Rapid choices retarget from the current composited frame; repeat, hidden, resize, close, language, and theme paths finish immediately without rebuilding pages or losing their state.
- Dashboard pages receive already queried/aggregated values for Overview, Timeline, Replay, Analytics, distributions, Focus Activity, calendar-based Monthly totals, Focus Items, and History; they own no SQL. Reusable responsive grids reflow dense metrics rather than forcing fixed columns.
- `MonthlyCalendarWidget` maps dense `DailyTotal` values into a compact read-only, Monday-first grid. Visual cells stay centered beneath full-width weekday slots, cap at 80×72px, and retain a 50px narrow-layout safety width. Dates and `h/min` durations occupy fixed first/second text slots, so activity never changes the date baseline. Every recorded day shares one pale theme-derived radial gradient centered on the cell with a neutral low-contrast border; today and hover remain informational without click selection or persistence queries.
- `SessionEditorDialog` validates local manual/edit fields and returns canonical Focus values.
- `SettingsDialog` uses a left category sidebar plus `QStackedWidget` for Appearance, Companion, Timer, Data, and About. It emits the original preferences; controllers continue to perform immediate/debounced atomic persistence.

## Statistics Flow

```text
bounded/all-session focus_sessions query
  -> allocate actual duration across local midnight
  -> DailyTotal / FocusItemTotal / HeatmapData / MonthlyStatistics
  -> DailyReplaySummary / FocusAnalyticsSnapshot
  -> Dashboard and Replay widgets
```

Each full Dashboard refresh creates one immutable, request-scoped `DashboardStatisticsSnapshot`. It reads the complete Session history once, derives Today, seven-day trend, Focus Item rankings, Analytics, recent records, and History from that same ordered collection, and is discarded after the refresh. Focus Activity keeps its independent bounded history query; Monthly and single-day Timeline remain bounded, and the current month reuses the snapshot's monthly result when applicable. No cross-refresh cache is introduced.

Countdown target is metadata only. All totals use whole-minute `duration_seconds`; sub-minute Focus Sessions are not saved, and legacy rows are cleaned once through a schema-v5 settings marker. Focus Activity, Timeline, Donut, and Monthly rendering never execute database queries from `paintEvent`.

Analytics presents Daily, Weekly, and Monthly through one segmented primary trend. Weekly and Analytics draw line/area trends, Replay maps 24 hourly totals to an equal-height heat band, Monthly uses a compact 50–80px-wide calendar whose active days share one duration-independent, theme-derived, center-symmetric radial gradient without a colored outline, and the donut visualizes proportional distribution. The calendar chooses one stable text color against the least favorable normal and hover gradient stop; inactive cells remain flat, and activity only populates the reserved second text line without shifting the fixed 12pt date. Focus Activity performs one bounded query whose nominal 365-day start is extended backward to Monday, producing 365–371 dense days and one stable 7×53 matrix with a complete first column. Daily is hover-only, Weekly maps natural-week totals to proportional bottom-up columns, and Cumulative maps running weekly totals to a monotonic square staircase. A mode change first blends the old cells into the opaque surface, then reveals the target matrix through a soft top-left-to-bottom-right per-cell wave; rapid selections coalesce to the latest target without moving the shared month axis. Opaque RGB hover interpolation targets one day or one full column, while a mouse-transparent callout is anchored above that target. Goal progress bars remain semantic completion indicators.

Focus Item management exposes Add, Rename, and Delete only. The Add dialog's 16 swatches emit stable hex values internally but display localized human color names; no runtime recolor signal exists. Delete impact is queried before confirmation; confirmed deletion removes linked sessions and the item in one SQLite transaction, then refreshes every aggregate surface. Active, pending, and recoverable items are protected from deletion.

## Recovery and Reliability

Active checkpoint v4 stores canonical `focus_item_id`, `focus_item_name`, `mode`, actual accumulated seconds, state, target, Note, timestamps, and recovery token. The loader maps v1–v3 `subject_*` / `study_mode` keys into the same dataclass. Recovery restores PAUSED and excludes app downtime. Pending saves use a unique database recovery token.

Settings use temp write, flush, fsync, and atomic replace. SQLite schema migration uses a single explicit transaction with version update and integrity checks. The application never deletes/recreates a failing user database.

## Desktop and Resources

`ApplicationPaths` is the only source for the bundled default companion and application icon. Frozen builds read bundled files from `sys._MEIPASS`; all writable files remain in `%LOCALAPPDATA%\DesktopFocusCompanion`.

`PetAssetManager` and `AppIconManager` validate, copy, resolve, and safely fall back. The runtime does not implement GIF animation, a companion status layer, or complex companion interaction mechanics. Live Focus state remains in `FocusPanel`; Dashboard presents aggregate history and analysis.

`TrayController.menu` is a shared `RoundedMenu` for the tray and desktop-companion right click. Its transparent top-level canvas and painted rounded surface prevent native rectangular corner artifacts while retaining ordinary `QMenu` actions. It exposes one Focus Center entry for the existing Dashboard window plus Settings, companion visibility, and Exit. Desktop-companion left click remains the only general entry for toggling the Focus Panel; recent-item selection stays inside that panel.

The Focus Panel owns a UI-only `PreFocusCountdownWidget` between its Idle and Active pages. Start parameters are frozen before the silent 3-2-1 animation, but `FocusSessionManager.start()` is called only by the completion signal. Closing or hiding the panel cancels the pending request, so the domain `TimerState`, SQLite data, countdown target, and recovery checkpoint remain untouched during pre-start.

## Internationalization and Themes

`LocalizationManager` owns the current `QLocale`, JSON catalog lookup, key-parity validation, and `language_changed`. Widgets retain raw values and reformat/retranslate on that signal. User-entered names and Notes are never translated.

`ThemeManager` owns six compatible but refined presets: Default, Lavender, Pink, Blue, Dark, and Charcoal. Charcoal is a neutral black-gray preset with pure-white primary text and silver-gray accents, while the existing purple-toned Dark preset remains unchanged. Each exposes semantic Canvas, Surface, Elevated, Accent, text, interaction, focus, status, chart-palette, and Heatmap tokens. Shared metrics define the typography hierarchy, 8pt-based spacing rhythm, control heights, radii, icon sizes, sidebar widths, and responsive breakpoint. Existing theme IDs and persisted settings remain unchanged; `charcoal` is appended as a new stable ID.

Runtime theme changes use a coordinated dual-snapshot transition. Every eligible visible application surface first keeps a complete source frame above the live window; after the new palette, QSS, icons, and custom-painted colors are applied, the fully rendered target frame is captured and painted beneath it. The source then fades out over 220ms with `OutCubic`, so the compositor never exposes a partially repainted Qt backing store. Transparent Focus Panel corners retain their alpha, rapid selections reuse the current composited frame, and a failed target capture falls back to a synchronously repainted instant switch instead of risking a black or blank frame. The desktop companion and transient popups remain excluded.

Typography is applied through `QApplication.setFont()` rather than a single QSS family. `ThemeManager.set_language()` selects Microsoft YaHei UI → Microsoft YaHei → DengXian → Noto Sans SC → SimHei for zh-CN, and Segoe UI with CJK fallbacks for en-US. `LocalizationManager.language_changed` is connected once during application creation, so existing controls, menus, dialogs, and custom-painted charts update immediately while the active theme and business state remain untouched.

Reusable Qt primitives are implemented by the internal `component_controls`, `component_layouts`, `component_widgets`, and `page_transition` modules; `app/ui/components.py` remains the stable compatibility facade and re-exports every existing public name. Dashboard table and Focus Activity internals similarly live in `dashboard_widgets`, while `dashboard.py` preserves its established imports and aliases. PageHeader, SectionSurface, MetricStrip, EmptyState, SegmentedControl, IconButton, ListRow, ResponsiveGrid, StatusPill, CircularTimerWidget, ThemedDateEdit, and DurationPicker therefore keep the same external contracts. DurationPicker exposes the existing integer-minute interface through separate scrollable hour/minute selectors. Every combo-style field inherits the shared wheel-safe selector behavior: a closed field never changes value from wheel input and forwards that input to its nearest scrolling page. While open, `AnimatedAnchoredPopup` classifies native wheel events at the owning or popup `QWindow` before Qt dispatches them to child widgets; gestures located over the anchor field or any popup surface directly browse the relevant scroll bar without activating an option, while external page input closes the popup and continues normally. Date fields translate those gestures into month browsing, while time fields route them to the focused or pointed hour/minute column. Ordinary content surfaces are flat with light separators; `apply_elevation` is reserved for floating or intentionally raised surfaces. Central QSS owns hover, pressed, checked, disabled, and keyboard-focus states for the app shell, both sidebars, Settings sections, Focus Panel, controls, menus, and dialogs. Its generated text is assembled from pure style fragments without changing selector order or bytes. `IconSystem` renders the same theme-aware line icon language for Dashboard, Settings, tray, and companion menus.

Legacy level-related values remain inside the pre-existing compatibility service so schema/data behavior does not change, but no UI, menu, notification, Replay, or Analytics presents them.

## Packaging

`DesktopFocusCompanion.spec` includes the default companion, all application icons, zh-CN/en-US catalogs, Qt plugins, and canonical application modules. It rejects third-party ICU DLLs discovered through the build host PATH because Qt for Windows requires the unversioned system ICU API. `build.ps1` invokes PyInstaller with `--clean`, then launches the packaged EXE against an isolated profile and requires its intentional clean exit; DLL/import error dialogs therefore fail the build.

`build-installer.ps1` compiles that onedir output with Inno Setup into a per-user installer under `dist\installer`. The fixed installer AppId is the upgrade boundary. Program files live under `%LOCALAPPDATA%\Programs\DesktopFocusCompanion`, while durable user state remains separately under `%LOCALAPPDATA%\DesktopFocusCompanion`; upgrades replace the complete program directory, and uninstall removes binaries and shell integration without deleting focus history or preferences. While the application is alive, its single-instance guard also owns a stable Windows named mutex matched by Inno Setup's `AppMutex`, so setup and uninstall stop with a tray-exit instruction instead of deleting locked files or scheduling reboot-time cleanup. Installer verification compiles with a fresh temporary AppId, installs a lower-version baseline, upgrades it, repeats the current-version install, launches the installed executable through the packaged-runtime gate, and then verifies clean uninstall, data preservation, and an unchanged Windows pending-file-operation queue without touching a real installation or startup entry.
## Development hardening boundaries

- `theme_tokens`, `theme_styles`, and `theme_transitions` separate tokens, byte-preserving QSS and snapshots; `theme.py` retains compatibility exports.
- `dashboard_builders`, `quick_panel_builders` and `settings_dialog_builders` group construction without recreating controls or changing signal order. `activity_layout` owns pure aggregation, geometry and hit-testing; `heatmap_widget` keeps rendering and interaction.
- `FocusItemMetricsSnapshot` and `ProgressStatisticsSnapshot` are operation-scoped read models, never cross-refresh caches. Project choices read the active item list once; totals/latest records share one history read. Progress reuses one date summary and raw duration sum.
- `timezones.system_timezone()` resolves Qt's system IANA identifier using standard-library ZoneInfo and bundled tzdata. Statistics pin a timezone during each operation; injected timezones stay fixed. Local dates define buckets, but UTC arithmetic determines interval shares and timeline positions on DST days. Running timers still use the monotonic clock.
- The record editor pins its timezone, preserves untouched original timestamps/seconds/duration, and edits start, end and effective duration independently. Missing wall times are rejected; repeated wall times require a fold choice while original folds survive unchanged. Repository updates preserve unchanged legacy precision and timer metadata.
- Checkpoint load/save/restore reject non-finite, negative and boolean durations before mutating state; JSON cannot contain NaN/Infinity. Cleanup diagnostics do not replace the original write error. Legacy v1–v4 readers, schema v1–v5 migrations, Subject adapters and Study aliases remain supported.
- `dev.ps1` injects a source-only isolated profile; production defaults are unchanged. `scripts/build_support.py` supplies canonical EXE metadata and verifies version/source/payload provenance. Build manifests are not user-data backups.

The installer smoke test compares pending operations as source/target pairs. New application/test paths fail; unrelated software activity warns. The system queue is never modified. See [Local development](development.md) for the quality and publication boundaries.
