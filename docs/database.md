# Desktop Focus Companion Database Schema v5

Desktop Focus Companion stores durable focus data in `%LOCALAPPDATA%\DesktopFocusCompanion\desktop-focus-companion.sqlite3`.

## focus_items

```text
id INTEGER PRIMARY KEY
name TEXT NOT NULL UNIQUE COLLATE NOCASE
color TEXT NOT NULL
is_favorite INTEGER NOT NULL
is_archived INTEGER NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

`color` remains active metadata. `is_favorite` and `is_archived` remain only for schema-v5 compatibility and have no current UI controls. Confirmed deletion removes all linked sessions first and the item second in one transaction.

## focus_sessions

```text
id INTEGER PRIMARY KEY
focus_item_id INTEGER NOT NULL -> focus_items(id)
focus_item_name TEXT NOT NULL
start_time TEXT NOT NULL
end_time TEXT NOT NULL
duration_seconds REAL NOT NULL
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
recovery_token TEXT NULL UNIQUE
mode TEXT NOT NULL CHECK stopwatch/countdown
target_duration_seconds REAL NULL
note TEXT NOT NULL
source TEXT NOT NULL CHECK timer/manual
```

`focus_item_name` is a historical snapshot. Rename does not rewrite old history. `duration_seconds` is the only aggregate input and is validated as at least 60 seconds in exact 60-second increments; Countdown target never inflates actual time. A one-time schema-v5 settings marker transaction removes legacy sub-minute rows and floors older fractional durations without adding or deleting columns.

Indexes cover start time, end time, Focus Item, and unique non-null recovery token.

## Other retained tables

- `settings`: Goal/Streak values and one-time structured preferences.
- `goal_celebrations`: prevents duplicate daily Goal notifications.
- `achievement_unlocks`: retained as an inert schema-compatible table; the current runtime does not read or write achievements.

## Migration v4 → v5

```text
subjects       -> focus_items
study_sessions -> focus_sessions
subject_id     -> focus_item_id
subject_name   -> focus_item_name
study_mode     -> mode
```

The migration preserves IDs, names, archive state, start/end, actual duration, creation time, recovery token, mode, and target. On the first run of the current lifecycle, legacy archived items and their linked sessions are permanently deleted and remaining Favorite flags are cleared atomically. A settings marker prevents deleted-all profiles from being silently reseeded later.

Every migration runs inside `BEGIN IMMEDIATE`. Statements, `PRAGMA user_version`, `quick_check`, and `foreign_key_check` succeed together or rollback together. Future/invalid schema stops startup without deleting the database.

Timestamps are timezone-aware UTC ISO 8601 strings. Analytics converts them into the current local timezone and proportionally allocates actual duration across local midnight.
