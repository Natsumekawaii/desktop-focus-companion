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
