"""Windows generic credentials, separately namespaced for each data profile."""

from __future__ import annotations

import ctypes
import hashlib
import sys
from ctypes import wintypes
from pathlib import Path


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class CredentialStore:
    def __init__(self, data_dir: Path) -> None:
        identity = hashlib.sha256(
            str(data_dir.resolve()).casefold().encode()
        ).hexdigest()[:24]
        self.target = f"DesktopFocusCompanion/DeepSeek/{identity}"
        self._session_key = ""

    def _api(self):
        if sys.platform != "win32":
            raise OSError("Windows credential storage is unavailable.")
        api = ctypes.WinDLL("Advapi32", use_last_error=True)
        api.CredWriteW.argtypes = (ctypes.POINTER(_Credential), wintypes.DWORD)
        api.CredWriteW.restype = wintypes.BOOL
        api.CredReadW.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_Credential)),
        )
        api.CredReadW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = (ctypes.c_void_p,)
        return api

    def read(self) -> str:
        if self._session_key:
            return self._session_key
        api = self._api()
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return ""
            raise OSError("Unable to read Windows credentials.")
        try:
            return ctypes.string_at(
                pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize
            ).decode("utf-8")
        finally:
            api.CredFree(pointer)

    def save(self, key: str) -> bool:
        key = key.strip()
        if not key or len(key) > 2000 or any(c.isspace() for c in key):
            raise ValueError("Invalid API key.")
        self._session_key = key
        try:
            api = self._api()
            blob = (ctypes.c_ubyte * len(key.encode())).from_buffer_copy(key.encode())
            credential = _Credential(
                Type=1,
                TargetName=self.target,
                CredentialBlobSize=len(blob),
                CredentialBlob=blob,
                Persist=2,
                UserName="DeepSeek",
            )
            if not api.CredWriteW(ctypes.byref(credential), 0):
                raise OSError("Unable to save Windows credentials.")
            return True
        except OSError:
            # Deliberately no plaintext fallback.
            return False

    def delete(self) -> None:
        self._session_key = ""
        api = self._api()
        if not api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
            raise OSError("Unable to remove Windows credentials.")
