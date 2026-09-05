"""Central translation catalog, language state, and locale-aware formatting."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from string import Formatter
from typing import Any

from PySide6.QtCore import QDate, QLocale, QObject, QTime, Signal

DEFAULT_LANGUAGE = "en-US"
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Language:
    """A supported locale shown by its stable code and native display name."""

    code: str
    native_name: str


SUPPORTED_LANGUAGES = (
    Language("zh-CN", "简体中文"),
    Language("en-US", "English"),
)
SUPPORTED_LANGUAGE_CODES = frozenset(language.code for language in SUPPORTED_LANGUAGES)


class LocalizationManager(QObject):
    """Own the active catalog and notify every open view of runtime changes."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._catalogs = {
            language.code: self._load_catalog(language.code)
            for language in SUPPORTED_LANGUAGES
        }
        self._validate_catalogs()
        self._language = DEFAULT_LANGUAGE
        self._locale = _qt_locale(DEFAULT_LANGUAGE)

    @property
    def language(self) -> str:
        return self._language

    @property
    def locale(self) -> QLocale:
        return self._locale

    def set_language(self, language: str) -> bool:
        """Switch the process locale immediately; return whether it changed."""
        normalized = language if language in SUPPORTED_LANGUAGE_CODES else DEFAULT_LANGUAGE
        if normalized == self._language:
            QLocale.setDefault(self._locale)
            return False
        self._language = normalized
        self._locale = _qt_locale(normalized)
        QLocale.setDefault(self._locale)
        self.language_changed.emit(normalized)
        return True

    def translate(self, key: str, **values: Any) -> str:
        """Resolve a semantic key with English fallback and named placeholders."""
        catalog = self._catalogs[self._language]
        text = catalog.get(key, self._catalogs[DEFAULT_LANGUAGE].get(key, key))
        if not values:
            return text
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            logger.exception("Invalid translation parameters for key %s", key)
            return text

    def _load_catalog(self, language: str) -> dict[str, str]:
        resource = files("app.i18n.locales").joinpath(f"{language}.json")
        raw = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
        ):
            raise RuntimeError(f"Invalid Desktop Focus Companion translation catalog: {language}")
        return raw

    def _validate_catalogs(self) -> None:
        reference_keys = set(self._catalogs[DEFAULT_LANGUAGE])
        for language, catalog in self._catalogs.items():
            missing = reference_keys - set(catalog)
            extra = set(catalog) - reference_keys
            if missing or extra:
                raise RuntimeError(
                    f"Translation catalog mismatch for {language}: "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            try:
                for text in catalog.values():
                    tuple(Formatter().parse(text))
            except ValueError as error:
                raise RuntimeError(
                    f"Invalid translation placeholder syntax for {language}"
                ) from error


def _qt_locale(language: str) -> QLocale:
    locale = QLocale(language.replace("-", "_"))
    QLocale.setDefault(locale)
    return locale


_LOCALIZATION = LocalizationManager()


def get_localization() -> LocalizationManager:
    return _LOCALIZATION


def tr(key: str, **values: Any) -> str:
    return _LOCALIZATION.translate(key, **values)


def format_date(value: date | datetime, *, long: bool = True) -> str:
    """Format a calendar date using the active locale."""
    current = value.date() if isinstance(value, datetime) else value
    if long:
        month_name = _LOCALIZATION.locale.standaloneMonthName(
            current.month, QLocale.FormatType.LongFormat
        )
        return tr(
            "date.long",
            year=current.year,
            month=month_name,
            month_number=current.month,
            day=current.day,
        )
    qt_date = QDate(current.year, current.month, current.day)
    return _LOCALIZATION.locale.toString(qt_date, QLocale.FormatType.ShortFormat)


def format_month_year(year: int, month: int) -> str:
    month_name = _LOCALIZATION.locale.standaloneMonthName(
        month, QLocale.FormatType.LongFormat
    )
    return tr("date.month_year", month=month_name, month_number=month, year=year)


def format_weekday(value: date | datetime, *, short: bool = True) -> str:
    current = value.date() if isinstance(value, datetime) else value
    mode = QLocale.FormatType.ShortFormat if short else QLocale.FormatType.LongFormat
    return _LOCALIZATION.locale.standaloneDayName(current.isoweekday(), mode)


def format_time(value: datetime) -> str:
    qt_time = QTime(value.hour, value.minute, value.second)
    return _LOCALIZATION.locale.toString(qt_time, QLocale.FormatType.ShortFormat)


def format_datetime(value: datetime) -> str:
    return tr("date.datetime", date=format_date(value), time=format_time(value))
