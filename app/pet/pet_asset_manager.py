"""Validation, storage, and fallback for static desktop pet images."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader, QPixmap

from app.core.paths import ApplicationPaths
from app.i18n import tr

SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 40_000_000
MAX_ASSET_FILE_BYTES = 100 * 1024 * 1024
logger = logging.getLogger(__name__)


class PetAssetError(RuntimeError):
    """Base error for static pet asset operations."""


class PetAssetImportError(PetAssetError):
    """Raised when a selected static pet image cannot be imported."""


@dataclass(frozen=True, slots=True)
class ResolvedPetAsset:
    path: Path
    using_default: bool
    fallback_reason: str | None = None


class PetAssetManager:
    """Import static images into managed storage and resolve a safe display asset."""

    def __init__(self, paths: ApplicationPaths) -> None:
        self._paths = paths

    def import_image(self, source_path: Path) -> str:
        source_path = source_path.expanduser().resolve()
        self._validate_import_source(source_path)
        self._paths.custom_pets_dir.mkdir(parents=True, exist_ok=True)
        destination = self._paths.custom_pets_dir / f"{uuid4().hex}{source_path.suffix.lower()}"
        try:
            shutil.copy2(source_path, destination)
            self._validate_image(destination)
        except (OSError, PetAssetImportError) as error:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            if isinstance(error, PetAssetImportError):
                raise
            raise PetAssetImportError(tr("error.pet_copy")) from error
        stored_path = destination.relative_to(self._paths.data_dir).as_posix()
        logger.info("Static pet image imported as %s", stored_path)
        return stored_path

    def resolve(self, custom_pet_path: str | None) -> ResolvedPetAsset:
        if custom_pet_path:
            custom_path = self._safe_custom_path(custom_pet_path)
            if custom_path is not None:
                try:
                    self._validate_image(custom_path)
                    return ResolvedPetAsset(custom_path, using_default=False)
                except PetAssetImportError:
                    logger.warning("Saved static pet asset is invalid: %s", custom_path)

        default_path = self._paths.default_pet_path
        try:
            self._validate_image(default_path)
        except PetAssetImportError as error:
            raise PetAssetError(tr("error.pet_default")) from error
        return ResolvedPetAsset(
            default_path,
            using_default=True,
            fallback_reason=(tr("error.pet_saved_custom") if custom_pet_path else None),
        )

    def load_pixmap(self, asset: ResolvedPetAsset) -> QPixmap:
        pixmap = QPixmap(str(asset.path))
        if pixmap.isNull():
            raise PetAssetError(tr("error.pet_render", name=asset.path.name))
        return pixmap

    def _validate_import_source(self, source_path: Path) -> None:
        if source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise PetAssetImportError(tr("error.pet_static_formats"))
        if not source_path.is_file():
            raise PetAssetImportError(tr("error.pet_missing"))
        self._validate_image(source_path)

    def _validate_image(self, image_path: Path) -> QSize:
        if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise PetAssetImportError(tr("error.pet_static_formats"))
        try:
            if image_path.stat().st_size > MAX_ASSET_FILE_BYTES:
                raise PetAssetImportError(tr("error.pet_file_size"))
        except OSError as error:
            raise PetAssetImportError(tr("error.pet_access")) from error
        reader = QImageReader(str(image_path))
        reader.setAutoTransform(True)
        if not reader.canRead():
            raise PetAssetImportError(tr("error.pet_read"))
        size = reader.size()
        if not size.isValid():
            raise PetAssetImportError(tr("error.pet_dimensions"))
        if size.width() > MAX_IMAGE_DIMENSION or size.height() > MAX_IMAGE_DIMENSION:
            raise PetAssetImportError(tr("error.pet_dimension_limit"))
        if size.width() * size.height() > MAX_IMAGE_PIXELS:
            raise PetAssetImportError(tr("error.pet_pixel_limit"))
        image = reader.read()
        if image.isNull():
            raise PetAssetImportError(tr("error.pet_corrupt"))
        return image.size()

    def _safe_custom_path(self, relative_path: str) -> Path | None:
        path_value = Path(relative_path)
        if path_value.is_absolute():
            return None
        custom_root = self._paths.custom_pets_dir.resolve()
        candidate = (self._paths.data_dir / path_value).resolve()
        if not candidate.is_relative_to(custom_root):
            return None
        return candidate
