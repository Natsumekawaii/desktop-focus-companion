"""Filesystem locations used by Desktop Focus Companion."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PET_RELATIVE_PATH = Path("default_pet") / "default.png"
APPLICATION_ICON_RELATIVE_PATH = Path("icons") / "desktop-focus-companion.ico"
LEGACY_DEFAULT_PET_RELATIVE_PATHS = (Path("default_pet") / "idle.png",)


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    """Resolved project, asset, and writable data locations."""

    project_root: Path
    assets_dir: Path
    data_dir: Path

    @classmethod
    def discover(cls) -> ApplicationPaths:
        """Discover paths from the installed source tree."""
        if getattr(sys, "frozen", False):
            project_root = Path(sys.executable).resolve().parent
            assets_dir = Path(getattr(sys, "_MEIPASS", project_root)) / "assets"
        else:
            project_root = Path(__file__).resolve().parents[2]
            assets_dir = project_root / "assets"
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA")
            data_root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        else:
            xdg_data_home = os.environ.get("XDG_DATA_HOME")
            data_root = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
        return cls(
            project_root=project_root,
            assets_dir=assets_dir,
            data_dir=data_root / "DesktopFocusCompanion",
        )

    def prepare_data_directory(self) -> None:
        """Create fresh writable storage without importing another product's data."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def default_pet_path(self) -> Path:
        """Return the single canonical bundled pet image path."""
        return self.assets_dir / DEFAULT_PET_RELATIVE_PATH

    @property
    def application_icon_path(self) -> Path:
        """Return the canonical multi-resolution application icon path."""
        return self.assets_dir / APPLICATION_ICON_RELATIVE_PATH

    @property
    def custom_pets_dir(self) -> Path:
        """Return the application-owned custom pet image directory."""
        return self.data_dir / "pets" / "custom"

    @property
    def custom_app_icons_dir(self) -> Path:
        """Return the application-owned custom application icon directory."""
        return self.data_dir / "icons" / "custom"

    @property
    def settings_path(self) -> Path:
        """Return the JSON settings file path."""
        return self.data_dir / "settings.json"

    @property
    def database_path(self) -> Path:
        """Return the primary SQLite database path."""
        return self.data_dir / "desktop-focus-companion.sqlite3"

    @property
    def logs_dir(self) -> Path:
        """Return the application log directory."""
        return self.data_dir / "logs"

    @property
    def active_session_path(self) -> Path:
        """Return the crash-recovery checkpoint path."""
        return self.data_dir / "active-session.json"

    @property
    def instance_lock_path(self) -> Path:
        """Return the per-user single-instance lock path."""
        return self.data_dir / "desktop-focus-companion.lock"
