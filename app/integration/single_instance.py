"""Per-user process lock preventing concurrent Desktop Focus Companion writers."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Self

from PySide6.QtCore import QLockFile

APPLICATION_MUTEX_NAME = "DesktopFocusCompanion-31BF15A5-C9F6-4850-B158-CEB3C598956C"


class _WindowsApplicationMutex:
    """Expose application lifetime to Windows installers without owning the mutex."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._handle: int | None = None
        self._kernel32: object | None = None

    def acquire(self) -> None:
        if sys.platform != "win32" or self._handle is not None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        handle = create_mutex(None, False, self._name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._kernel32 = kernel32
        self._handle = int(handle)

    def release(self) -> None:
        if self._handle is None or self._kernel32 is None:
            return
        close_handle = self._kernel32.CloseHandle  # type: ignore[attr-defined]
        close_handle.argtypes = (ctypes.c_void_p,)
        close_handle.restype = ctypes.c_int
        close_handle(self._handle)
        self._handle = None
        self._kernel32 = None


class SingleInstanceGuard:
    """Hold a QLockFile for the complete application event-loop lifetime."""

    def __init__(self, lock_path: Path) -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(lock_path))
        self._lock.setStaleLockTime(0)
        self._acquired = False
        self._application_mutex = _WindowsApplicationMutex(APPLICATION_MUTEX_NAME)

    def acquire(self) -> bool:
        self._acquired = self._lock.tryLock(0)
        if self._acquired:
            try:
                self._application_mutex.acquire()
            except Exception:
                self._lock.unlock()
                self._acquired = False
                raise
        return self._acquired

    def release(self) -> None:
        if self._acquired:
            self._lock.unlock()
            self._application_mutex.release()
            self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    def __enter__(self) -> Self:
        if not self.acquire():
            raise RuntimeError("Desktop Focus Companion is already running.")
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
