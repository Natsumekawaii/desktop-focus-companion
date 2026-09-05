"""Desktop Focus Companion localization infrastructure and locale-aware formatting."""

from app.i18n.translator import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    Language,
    LocalizationManager,
    format_date,
    format_datetime,
    format_month_year,
    format_time,
    format_weekday,
    get_localization,
    tr,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "Language",
    "LocalizationManager",
    "format_date",
    "format_datetime",
    "format_month_year",
    "format_time",
    "format_weekday",
    "get_localization",
    "tr",
]
