"""Tests for static pet validation, ownership, and safe fallback."""

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from app.core.paths import ApplicationPaths
from app.pet.pet_asset_manager import (
    MAX_ASSET_FILE_BYTES,
    PetAssetImportError,
    PetAssetManager,
)


@pytest.fixture
def application_paths(tmp_path: Path) -> ApplicationPaths:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _write_image(paths.default_pet_path, "PNG", transparent=True)
    return paths


@pytest.mark.parametrize(
    ("extension", "image_format"),
    [
        (".png", "PNG"),
        (".jpg", "JPEG"),
        (".jpeg", "JPEG"),
        (".webp", "WEBP"),
    ],
)
def test_static_images_are_copied_with_collision_safe_names(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
    extension: str,
    image_format: str,
) -> None:
    source_path = tmp_path / f"my-pet{extension}"
    _write_image(source_path, image_format, transparent=extension == ".png")
    manager = PetAssetManager(application_paths)

    first_relative_path = manager.import_image(source_path)
    second_relative_path = manager.import_image(source_path)

    assert first_relative_path != second_relative_path
    assert first_relative_path.startswith("pets/custom/")
    assert (application_paths.data_dir / first_relative_path).is_file()
    assert source_path.is_file()
    resolved = manager.resolve(first_relative_path)
    assert not resolved.using_default
    assert resolved.path == application_paths.data_dir / first_relative_path


def test_gif_is_rejected_with_static_only_message(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
) -> None:
    gif_path = tmp_path / "animated.gif"
    gif_path.write_bytes(b"GIF89a")

    with pytest.raises(PetAssetImportError, match="static desktop companion images only"):
        PetAssetManager(application_paths).import_image(gif_path)

    assert not application_paths.custom_pets_dir.exists()


def test_invalid_image_is_rejected_without_creating_owned_file(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
) -> None:
    invalid_image = tmp_path / "broken.png"
    invalid_image.write_text("not an image", encoding="utf-8")

    with pytest.raises(PetAssetImportError, match="readable image"):
        PetAssetManager(application_paths).import_image(invalid_image)

    assert not application_paths.custom_pets_dir.exists()


@pytest.mark.parametrize(
    "saved_path",
    [
        "pets/custom/missing.png",
        "../outside.png",
        "pets/custom/legacy.gif",
        "pets/custom/corrupted.png",
    ],
)
def test_invalid_or_legacy_saved_asset_falls_back_to_default(
    qt_application,
    application_paths: ApplicationPaths,
    saved_path: str,
) -> None:
    if saved_path.endswith(("legacy.gif", "corrupted.png")):
        saved_asset = application_paths.data_dir / saved_path
        saved_asset.parent.mkdir(parents=True, exist_ok=True)
        saved_asset.write_bytes(b"GIF89a" if saved_path.endswith(".gif") else b"broken")
    resolved = PetAssetManager(application_paths).resolve(saved_path)

    assert resolved.using_default
    assert resolved.path == application_paths.default_pet_path
    assert resolved.fallback_reason is not None


def test_oversized_supported_image_is_rejected_before_decode(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
) -> None:
    huge = tmp_path / "huge.png"
    with huge.open("wb") as handle:
        handle.seek(MAX_ASSET_FILE_BYTES)
        handle.write(b"x")

    with pytest.raises(PetAssetImportError, match="100 MB"):
        PetAssetManager(application_paths).import_image(huge)


def test_bundled_default_pet_has_real_transparency(qt_application) -> None:
    default_path = ApplicationPaths.discover().default_pet_path
    image = QImage(str(default_path))

    assert default_path.name == "default.png"
    assert default_path.is_file()
    assert not image.isNull()
    assert min(image.width(), image.height()) >= 512
    assert max(image.width(), image.height()) <= 8192
    assert image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(image.width() - 1, image.height() - 1).alpha() == 0


def _write_image(path: Path, image_format: str, transparent: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(96, 64, QImage.Format.Format_ARGB32)
    alpha = 180 if transparent else 255
    image.fill(QColor(145, 95, 210, alpha))
    assert image.save(str(path), image_format)
