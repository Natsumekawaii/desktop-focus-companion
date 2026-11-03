[English](data-safety.md) | [简体中文](data-safety.zh-CN.md)

# Automatic Persistence and Data Safety

Desktop Focus Companion 1.0 is local-first and has no Save/Apply workflow.

## Immediate persistence

- Timer Finish: immediate `FocusSessionRepository` transaction.
- Manual Entry confirmation: immediate transaction with `source=manual`.
- Focus Item create-with-color and rename: immediate transactions.
- Confirmed Focus Item deletion: linked sessions and the item are permanently removed in one transaction; failure rolls back both.
- Goal/Streak preferences: immediate SQLite settings update.
- General/desktop-companion/focus/appearance settings: immediate or 250 ms debounce atomic JSON update.

## Atomic settings

Settings serialize to a same-directory temporary file, flush, fsync, then `os.replace` the live file. Corrupt JSON is preserved as a timestamped diagnostic copy and defaults are loaded.

## SQLite reliability

- foreign keys enabled per connection;
- 5 second busy timeout;
- parameterized repository operations;
- explicit migration transaction and rollback;
- post-migration `quick_check` and `foreign_key_check`;
- recovery-token uniqueness for idempotent pending save.

The application never repairs a failure by deleting the database.

The explicitly approved lifecycle upgrade is the exception: its first-run transaction permanently removes legacy `is_archived=1` items and their linked sessions, clears remaining Favorite flags, and writes an initialization marker. The transaction either completes fully or rolls back fully. Current active/pending/recovery Focus Items cannot be deleted.

The minute-precision upgrade is also explicit and one-time: a separate schema-v5 transaction deletes legacy Focus Sessions shorter than 60 seconds, floors every remaining non-integral duration to complete minutes, and writes its initialization marker. If any statement fails, the sessions and marker both roll back.

## Active-session checkpoint

`active-session.json` v4 contains Focus Item identity/snapshot, start, confirmed accumulated actual duration, timer state, mode, optional target, Note, recovery token, last checkpoint, and optional pending end. It is written atomically on state changes and every 30 seconds.

The loader reads v1/v2/v3 legacy keys. Recovery restores PAUSED and never adds application downtime. Invalid checkpoint data is preserved for diagnosis and ignored without modifying SQLite.

## User resources and build isolation

User database, Settings, custom desktop-companion images, custom application icons, any legacy export files, and logs live under `%LOCALAPPDATA%\DesktopFocusCompanion`. PyInstaller `build/` and `dist/` contain no user data. Cleaning those folders cannot remove the AppData tree.

Missing/corrupt custom resources fall back to the bundled default while the application remains usable. Reset clears only the selected custom resource setting and preserves unrelated preferences.

## Deliberately absent backup scope

Desktop Focus Companion does not provide scheduled backup, ZIP backup, manifest, retention, restore manager, backup history, or CSV export.

## Optional AI and data leaving the device

The development-only DeepSeek assistant is disabled by default. No model or completion request is made on startup. Explicit Key testing calls only the official model-list endpoint; sending a chat after consent calls the official HTTPS completion endpoint. Conversations and the relevant focus records, names and optionally notes are transmitted to DeepSeek, not an entire database file. API charges and the provider's data handling apply. No third-party proxy is configurable.

Each data profile stores chats and non-secret preferences in `agent/conversations.sqlite3`. Deleting a chat never deletes focus records; it does not request deletion of data already processed by the provider. Chat files are ordinary local SQLite, not encrypted. There is no cross-conversation memory. Only complete turns are sent as prior context; older turns may be omitted while remaining available locally.

Keys use Windows Credential Manager with a target derived from the resolved data directory. Development and installed profiles cannot read each other's Key or chats. If secure storage fails, the Key remains in memory for that run and AI is disabled again after restart. Never paste a Key into a chat or issue. Use AI configuration to remove a stored Key before deleting the data profile. Normal uninstall preserves user data and credentials; it does not silently revoke your DeepSeek Key.

Only allowlisted record operations are available: no SQL, shell, arbitrary files, settings, project management or timer control. Model text and database notes are not authorization. A complete single creation can save automatically; updates, deletions, overlapping creations and every batch require an explicit preview confirmation. Ambiguous fields require clarification. Maximums are 50 changes per plan, one plan per turn and eight completion requests per turn.

`apply_changes` validates exact record/item snapshots, the time zone and overlap set inside a SQLite transaction, preserves unchanged effective duration and timer metadata, and stores a minimal idempotency receipt in the existing settings table. The main database schema stays at v5. Cancellation before commit rolls back the batch. A committed transaction is never undone by Stop or a network failure; its receipt repairs an interrupted chat status after restart, without replaying the operation. Tool previews may contain private record data, so screenshots should use synthetic profiles.

Markdown cannot execute HTML or fetch images/files. Network headers, keys, completion bodies and reasoning are not logged. Reasoning content is kept privately with the local conversation because DeepSeek requires it for tool continuation; the interface only shows thinking status. Redaction is defense in depth, not permission to put secrets in project notes or chat.
