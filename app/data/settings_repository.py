"""Fault-tolerant JSON settings persistence."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.paths import LEGACY_DEFAULT_PET_RELATIVE_PATHS
from app.core.theme import DEFAULT_COLOR_THEME, normalize_color_theme
from app.focus_mode import FocusMode, validate_target_duration
from app.i18n import DEFAULT_LANGUAGE
from app.i18n.translator import SUPPORTED_LANGUAGE_CODES, tr

MIN_PET_SIZE_PERCENT = 50
MAX_PET_SIZE_PERCENT = 150
DEFAULT_PET_SIZE_PERCENT = 100
logger = logging.getLogger(__name__)
LEGACY_BACKUP_SETTING_KEYS = frozenset({"backup_interval_days", "backup_retention_count"})
LEGACY_THEME_SETTING_KEY = "menu_color_scheme"


class SettingsSaveError(RuntimeError):
    """Raised when application settings cannot be written safely."""


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Persisted application and static desktop pet preferences."""

    pet_x: int | None = None
    pet_y: int | None = None
    pet_size_percent: int = DEFAULT_PET_SIZE_PERCENT
    custom_pet_path: str | None = None
    custom_app_icon_path: str | None = None
    always_on_top: bool = True
    notifications_enabled: bool = True
    start_with_windows: bool = False
    language: str = DEFAULT_LANGUAGE
    color_theme: str = DEFAULT_COLOR_THEME
    default_focus_mode: str = FocusMode.STOPWATCH.value
    default_focus_target_seconds: int = 25 * 60

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> AppSettings:
        """Create validated settings while falling back per invalid field."""
        return cls(
            pet_x=_optional_integer(values.get("pet_x")),
            pet_y=_optional_integer(values.get("pet_y")),
            pet_size_percent=_bounded_size(values.get("pet_size_percent")),
            custom_pet_path=_custom_pet_path(values.get("custom_pet_path")),
            custom_app_icon_path=_optional_string(values.get("custom_app_icon_path")),
            always_on_top=_boolean(values.get("always_on_top"), True),
            notifications_enabled=_boolean(values.get("notifications_enabled"), True),
            start_with_windows=_boolean(values.get("start_with_windows"), False),
            language=_language(values.get("language")),
            color_theme=normalize_color_theme(
                values.get("color_theme", values.get(LEGACY_THEME_SETTING_KEY))
            ),
            default_focus_mode=_focus_mode(values.get("default_focus_mode")),
            default_focus_target_seconds=_focus_target(
                values.get("default_focus_target_seconds")
            ),
        )


class SettingsRepository:
    """Read and atomically write Desktop Focus Companion settings as local JSON."""

    def __init__(self, settings_path: Path) -> None:
        self._settings_path = settings_path

    def load(self) -> AppSettings:
        """Load settings, returning safe defaults for missing/corrupt data."""
        try:
            raw_settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return AppSettings()
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            logger.error("Settings recovery used defaults for %s: %s", self._settings_path, error)
            self._preserve_corrupt_settings()
            return AppSettings()

        if not isinstance(raw_settings, dict):
            return AppSettings()
        settings = AppSettings.from_mapping(raw_settings)
        if _is_legacy_default_pet_path(raw_settings.get("custom_pet_path")) or any(
            key in raw_settings for key in LEGACY_BACKUP_SETTING_KEYS
        ) or LEGACY_THEME_SETTING_KEY in raw_settings:
            try:
                self.save(settings)
            except SettingsSaveError:
                logger.warning("Unable to persist legacy default-pet path migration")
        return settings

    def save(self, settings: AppSettings) -> None:
        """Persist settings atomically so interrupted writes do not corrupt them."""
        temporary_path = self._settings_path.with_suffix(".json.tmp")
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._settings_path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SettingsSaveError(tr("error.settings_save")) from error

    def _preserve_corrupt_settings(self) -> None:
        if not self._settings_path.is_file():
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = self._settings_path.with_name(f"settings.corrupt-{timestamp}.json")
        try:
            shutil.copy2(self._settings_path, destination)
            logger.warning("Corrupted settings preserved at %s", destination)
        except OSError:
            logger.exception("Unable to preserve corrupted settings file")


def _optional_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bounded_size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_PET_SIZE_PERCENT
    return max(MIN_PET_SIZE_PERCENT, min(MAX_PET_SIZE_PERCENT, value))


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped_value = value.strip()
    return stripped_value or None


def _custom_pet_path(value: object) -> str | None:
    """Migrate removed bundled-default paths without touching managed custom pets."""
    path = _optional_string(value)
    if path is None or _is_legacy_default_pet_path(path):
        return None
    return path


def _is_legacy_default_pet_path(value: object) -> bool:
    path = _optional_string(value)
    if path is None:
        return False
    normalized = path.replace("\\", "/").casefold()
    for legacy_path in LEGACY_DEFAULT_PET_RELATIVE_PATHS:
        legacy = legacy_path.as_posix().casefold()
        bundled = f"assets/{legacy}"
        if normalized in {legacy, bundled} or normalized.endswith(f"/{bundled}"):
            return True
    return False


def _boolean(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _language(value: object) -> str:
    return value if isinstance(value, str) and value in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE


def _focus_mode(value: object) -> str:
    try:
        return FocusMode(str(value)).value
    except ValueError:
        return FocusMode.STOPWATCH.value


def _focus_target(value: object) -> int:
    try:
        return int(validate_target_duration(value))
    except ValueError:
        return 25 * 60
