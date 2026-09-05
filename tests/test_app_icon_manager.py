"""Tests for custom application icon validation, storage, and fallback."""

from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QIcon, QImage

from app.core.app_icon_manager import AppIconImportError, AppIconManager
from app.core.paths import ApplicationPaths


@pytest.fixture
def application_paths(tmp_path: Path) -> ApplicationPaths:
    paths = ApplicationPaths(
        project_root=tmp_path,
        assets_dir=tmp_path / "assets",
        data_dir=tmp_path / "data",
    )
    _write_icon(paths.application_icon_path, "ICO")
    return paths


@pytest.mark.parametrize(
    ("extension", "image_format"),
    [
        (".png", "PNG"),
        (".jpg", "JPEG"),
        (".jpeg", "JPEG"),
        (".webp", "WEBP"),
        (".ico", "ICO"),
    ],
)
def test_supported_icons_are_validated_and_copied_with_unique_names(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
    extension: str,
    image_format: str,
) -> None:
    source = tmp_path / f"my-icon{extension}"
    _write_icon(source, image_format)
    manager = AppIconManager(application_paths)

    first = manager.import_icon(source)
    second = manager.import_icon(source)

    assert first != second
    assert first.startswith("icons/custom/")
    assert source.is_file()
    resolved = manager.resolve(first)
    assert not resolved.using_default
    assert resolved.path == application_paths.data_dir / first
    assert not QIcon(str(resolved.path)).isNull()


@pytest.mark.parametrize(
    "saved_path",
    ["icons/custom/missing.png", "../outside.png", "icons/custom/broken.ico"],
)
def test_missing_unsafe_or_corrupt_saved_icon_falls_back_to_default(
    qt_application,
    application_paths: ApplicationPaths,
    saved_path: str,
) -> None:
    if saved_path.endswith("broken.ico"):
        broken = application_paths.data_dir / saved_path
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b"not an icon")

    resolved = AppIconManager(application_paths).resolve(saved_path)

    assert resolved.using_default
    assert resolved.path == application_paths.application_icon_path
    assert resolved.fallback_reason is not None


def test_invalid_icon_is_rejected_without_creating_a_managed_copy(
    qt_application,
    application_paths: ApplicationPaths,
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"not an image")

    with pytest.raises(AppIconImportError, match="readable"):
        AppIconManager(application_paths).import_icon(invalid)

    assert not application_paths.custom_app_icons_dir.exists()


def _write_icon(path: Path, image_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(96, 96, QImage.Format.Format_ARGB32)
    image.fill(QColor(30, 170, 95, 255))
    assert image.save(str(path), image_format)
