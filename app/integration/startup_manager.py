"""Safe, per-user Windows startup registration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.i18n import tr

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Desktop Focus Companion"


class StartupManagerError(RuntimeError):
    """Raised when the current-user startup entry cannot be changed."""


class WindowsStartupManager:
    """Manage only this application's HKCU Run value; no admin rights required."""

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def build_command(self) -> str:
        """Return the packaged exe or development pythonw command."""
        if getattr(sys, "frozen", False):
            arguments = [str(Path(sys.executable).resolve())]
        else:
            python_path = Path(sys.executable).resolve()
            pythonw_path = python_path.with_name("pythonw.exe")
            executable = pythonw_path if pythonw_path.exists() else python_path
            arguments = [str(executable), str((self._project_root / "main.py").resolve())]
        return subprocess.list2cmdline(arguments)

    def is_enabled(self) -> bool:
        if not self.supported:
            return False
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value) == self.build_command()
        except FileNotFoundError:
            return False
        except OSError as error:
            raise StartupManagerError(tr("error.startup_read")) from error

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported:
            if enabled:
                raise StartupManagerError(tr("error.startup_unsupported"))
            return
        try:
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                if enabled:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, self.build_command())
                else:
                    try:
                        winreg.DeleteValue(key, VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as error:
            raise StartupManagerError(tr("error.startup_update")) from error
