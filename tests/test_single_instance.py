"""Single-instance locking protects the per-user data directory."""

import ctypes
import sys
from pathlib import Path

import pytest

from app.integration.single_instance import APPLICATION_MUTEX_NAME, SingleInstanceGuard


def test_only_one_guard_can_hold_the_same_lock(tmp_path: Path) -> None:
    first = SingleInstanceGuard(tmp_path / "desktop-focus-companion.lock")
    second = SingleInstanceGuard(tmp_path / "desktop-focus-companion.lock")

    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows installer mutex")
def test_guard_exposes_and_releases_the_installer_mutex(tmp_path: Path) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_mutex = kernel32.OpenMutexW
    open_mutex.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    open_mutex.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_int
    guard = SingleInstanceGuard(tmp_path / "desktop-focus-companion.lock")
    preexisting_handle = open_mutex(0x00100000, False, APPLICATION_MUTEX_NAME)
    mutex_already_existed = bool(preexisting_handle)
    if preexisting_handle:
        assert close_handle(preexisting_handle)

    assert guard.acquire()
    handle = open_mutex(0x00100000, False, APPLICATION_MUTEX_NAME)
    assert handle
    assert close_handle(handle)

    guard.release()
    remaining_handle = open_mutex(0x00100000, False, APPLICATION_MUTEX_NAME)
    assert bool(remaining_handle) is mutex_already_existed
    if remaining_handle:
        assert close_handle(remaining_handle)
