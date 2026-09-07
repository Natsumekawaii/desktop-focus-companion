[English](database.md) | [简体中文](database.zh-CN.md)

# Desktop Focus Companion 数据库结构 v5

Desktop Focus Companion 将持久化专注数据保存在 `%LOCALAPPDATA%\DesktopFocusCompanion\desktop-focus-companion.sqlite3`。

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

`color` 仍是有效元数据。`is_favorite` 和 `is_archived` 只为 schema v5 兼容性保留，当前界面不提供相关控件。确认删除时，会在同一事务中先删除所有关联记录，再删除项目。

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

`focus_item_name` 是历史名称快照；重命名项目不会重写旧记录。`duration_seconds` 是唯一统计输入，必须至少为 60 秒并精确到完整分钟；倒计时目标不会放大实际时长。一次性的 schema v5 设置标记事务会删除旧版不足一分钟的记录，并将旧的非整分钟时长向下取整，而不增删数据库列。

索引覆盖开始时间、结束时间、专注项目，以及非空恢复令牌的唯一性。

## 其他保留表

- `settings`：保存目标／连续专注数值及一次性结构化偏好。
- `goal_celebrations`：防止重复显示每日目标通知。
- `achievement_unlocks`：作为不活动的兼容表保留；当前运行时不读取或写入成就。

## 从 v4 迁移到 v5

```text
subjects       -> focus_items
study_sessions -> focus_sessions
subject_id     -> focus_item_id
subject_name   -> focus_item_name
study_mode     -> mode
```

迁移会保留 ID、名称、归档状态、起止时间、实际时长、创建时间、恢复令牌、模式和目标。当前生命周期首次运行时，旧版归档项目及其关联记录会被永久删除，剩余收藏标记会被原子清除。设置标记可防止已删除全部项目的用户配置日后被静默重新初始化。

每次迁移都在 `BEGIN IMMEDIATE` 中执行。所有语句、`PRAGMA user_version`、`quick_check` 和 `foreign_key_check` 必须一起成功，否则全部回滚。遇到未来版本或无效 schema 时，应用会停止启动，但不会删除数据库。

时间戳使用带时区的 UTC ISO 8601 字符串。统计功能会将其转换到当前本地时区，并按比例把实际时长分配到跨越的本地自然日。
