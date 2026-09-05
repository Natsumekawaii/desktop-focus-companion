"""Validation, managed storage, and fallback for application icons."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QImageReader

from app.core.paths import ApplicationPaths
from app.i18n import tr

SUPPORTED_APP_ICON_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".ico"})
MAX_APP_ICON_DIMENSION = 8192
MAX_APP_ICON_PIXELS = 40_000_000
MAX_APP_ICON_FILE_BYTES = 100 * 1024 * 1024
logger = logging.getLogger(__name__)


class AppIconError(RuntimeError):
    """Base error for application icon operations."""


class AppIconImportError(AppIconError):
    """Raised when a selected application icon cannot be imported."""


@dataclass(frozen=True, slots=True)
class ResolvedAppIcon:
    path: Path
    using_default: bool
    fallback_reason: str | None = None


class AppIconManager:
    """Import validated icons into managed storage and resolve a safe icon."""

    def __init__(self, paths: ApplicationPaths) -> None:
        self._paths = paths

    def import_icon(self, source_path: Path) -> str:
        source_path = source_path.expanduser().resolve()
        self._validate_import_source(source_path)
        self._paths.custom_app_icons_dir.mkdir(parents=True, exist_ok=True)
        destination = (
            self._paths.custom_app_icons_dir
            / f"{uuid4().hex}{source_path.suffix.lower()}"
        )
        try:
            shutil.copy2(source_path, destination)
            self._validate_icon(destination)
        except (OSError, AppIconImportError) as error:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, AppIconImportError):
                raise
            raise AppIconImportError(tr("error.app_icon_copy")) from error
        stored_path = destination.relative_to(self._paths.data_dir).as_posix()
        logger.info("Application icon imported as %s", stored_path)
        return stored_path

    def resolve(self, custom_app_icon_path: str | None) -> ResolvedAppIcon:
        if custom_app_icon_path:
            custom_path = self._safe_custom_path(custom_app_icon_path)
            if custom_path is not None:
                try:
                    self._validate_icon(custom_path)
                    return ResolvedAppIcon(custom_path, using_default=False)
                except AppIconImportError:
                    logger.warning("Saved application icon is invalid: %s", custom_path)

        default_path = self._paths.application_icon_path
        try:
            self._validate_icon(default_path)
        except AppIconImportError as error:
            raise AppIconError(tr("error.app_icon_default")) from error
        return ResolvedAppIcon(
            default_path,
            using_default=True,
            fallback_reason=(
                tr("error.app_icon_saved_custom") if custom_app_icon_path else None
            ),
        )

    def _validate_import_source(self, source_path: Path) -> None:
        if source_path.suffix.lower() not in SUPPORTED_APP_ICON_EXTENSIONS:
            raise AppIconImportError(tr("error.app_icon_formats"))
        if not source_path.is_file():
            raise AppIconImportError(tr("error.app_icon_missing"))
        self._validate_icon(source_path)

    def _validate_icon(self, icon_path: Path) -> QSize:
        if icon_path.suffix.lower() not in SUPPORTED_APP_ICON_EXTENSIONS:
            raise AppIconImportError(tr("error.app_icon_formats"))
        try:
            if icon_path.stat().st_size > MAX_APP_ICON_FILE_BYTES:
                raise AppIconImportError(tr("error.app_icon_file_size"))
        except OSError as error:
            raise AppIconImportError(tr("error.app_icon_access")) from error
        reader = QImageReader(str(icon_path))
        reader.setAutoTransform(True)
        if not reader.canRead():
            raise AppIconImportError(tr("error.app_icon_read"))
        size = reader.size()
        if not size.isValid():
            raise AppIconImportError(tr("error.app_icon_dimensions"))
        if size.width() > MAX_APP_ICON_DIMENSION or size.height() > MAX_APP_ICON_DIMENSION:
            raise AppIconImportError(tr("error.app_icon_dimension_limit"))
        if size.width() * size.height() > MAX_APP_ICON_PIXELS:
            raise AppIconImportError(tr("error.app_icon_pixel_limit"))
        image = reader.read()
        if image.isNull():
            raise AppIconImportError(tr("error.app_icon_corrupt"))
        if QIcon(str(icon_path)).isNull():
            raise AppIconImportError(tr("error.app_icon_render"))
        return image.size()

    def _safe_custom_path(self, relative_path: str) -> Path | None:
        path_value = Path(relative_path)
        if path_value.is_absolute():
            return None
        custom_root = self._paths.custom_app_icons_dir.resolve()
        candidate = (self._paths.data_dir / path_value).resolve()
        if not candidate.is_relative_to(custom_root):
            return None
        return candidate
