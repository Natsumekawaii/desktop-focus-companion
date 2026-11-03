[English](CHANGELOG.md) | [简体中文](CHANGELOG.zh-CN.md)

# Changelog

All notable changes to Desktop Focus Companion are documented here. Versions follow [Semantic Versioning](https://semver.org/), and dates use ISO 8601.

## [Unreleased]

## [1.0.1] - 2026-11-04

### Fixed

- Preserve original timestamps, actual Focus duration and timer metadata when editing only notes or the Focus Item; edit start, end and actual duration independently.
- Reject invalid recovery durations before changing timer state and keep diagnostic copies of damaged recovery files.
- Use system IANA time zones and UTC interval arithmetic for daylight-saving transitions, repeated local times and cross-midnight statistics.
- Report startup, persistence and refresh failures without silently presenting a failed operation as successful.

### Added

- Isolated source-development profiles with synthetic demo data, an explicit reset command and independent instance locks.
- Fast, documentation-only and full quality checks with timing reports; build provenance, stale-artifact checks and bounded installer smoke tests.

### Changed

- Reduce duplicate statistics reads and isolate Qt test resources without changing normal layouts or production data locations.
- Harden release publishing against overwriting existing assets; keep local validation builds separate from published installers.
- Split all public documentation, contribution templates, Issue Forms, and release notes into linked English and Simplified Chinese versions.
- Improve the README product tour and show all six themes in compact, localized contact sheets.

## [1.0.0] - 2026-09-05

### Added

- Local-first Stopwatch and Countdown Focus sessions with pause, resume, recovery, notes, and manual entry.
- Movable, resizable desktop companion with custom image and application icon support.
- Responsive Focus Center with Overview, true-time Timeline, Analytics, Monthly, Focus Items, History, and Daily Replay.
- Focus Item colors, compact management cards, custom selectors, animated tooltips, and lightweight page transitions.
- Simplified Chinese and English interfaces with Default, Lavender, Pink, Blue, Dark, and Charcoal themes.
- Per-user Windows installer, Start menu shortcut, optional desktop shortcut, tray integration, and safe upgrade/uninstall behavior.
- PyInstaller and Inno Setup build pipelines with packaged-runtime and isolated installer smoke tests.

### Privacy

- No account, cloud sync, analytics telemetry, or advertising service.
- User data remains under `%LOCALAPPDATA%\DesktopFocusCompanion` and is preserved by normal upgrades and uninstall.

[Unreleased]: https://github.com/Natsumekawaii/desktop-focus-companion/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/Natsumekawaii/desktop-focus-companion/releases/tag/v1.0.1
[1.0.0]: https://github.com/Natsumekawaii/desktop-focus-companion/releases/tag/v1.0.0
