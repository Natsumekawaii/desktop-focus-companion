"""Preflight checks and provenance for local, explicitly unpublished builds."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[1]


def compiler_version(compiler: str) -> str:
    import winreg

    key_name = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view) as key:
                    location = Path(winreg.QueryValueEx(key, "InstallLocation")[0])
                    if (location / "ISCC.exe").is_file() and (
                        compiler == "auto"
                        or (location / "ISCC.exe").resolve() == Path(compiler).resolve()
                    ):
                        return str(winreg.QueryValueEx(key, "DisplayVersion")[0])
            except FileNotFoundError:
                continue
    raise RuntimeError("Cannot verify this Inno Setup installation/version.")


def pinned_dependencies(root: Path = ROOT, *, build: bool = True) -> dict[str, str]:
    names = ["requirements.txt", "requirements-dev.txt"]
    if build:
        names.append("requirements-build.txt")
    result: dict[str, str] = {}
    for filename in names:
        for line in (root / filename).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r ")):
                continue
            match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", line)
            if not match:
                raise ValueError(f"Unpinned dependency in {filename}: {line}")
            name, version = match.groups()
            key = name.lower().replace("_", "-")
            if key in result and result[key] != version:
                raise ValueError(f"Conflicting dependency pin: {name}")
            result[key] = version
    return result


def preflight(*, compiler: str | None = None, tag: str | None = None) -> dict[str, str]:
    tools = json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))
    if platform.python_version() != tools["python"]:
        raise RuntimeError(
            f"Build requires Python {tools['python']}, found {platform.python_version()}."
        )
    if not re.fullmatch(r"\d+\.\d+\.\d+", __version__):
        raise ValueError("Application version must be a numeric semantic version.")
    if tag is not None and tag != f"v{__version__}":
        raise ValueError("Tag and application versions differ.")
    for suffix in (".md", ".zh-CN.md"):
        path = ROOT / ".github" / "release-notes" / f"v{__version__}{suffix}"
        if not path.is_file() or __version__ not in path.read_text(encoding="utf-8"):
            raise ValueError(f"Missing or mismatched release notes: {path.name}")
    for name, expected in pinned_dependencies().items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError(
                f"{name}: expected {expected}, installed {actual}; install the pinned requirements."
            )
    if shutil.which("git") is None:
        raise RuntimeError("Git is required on PATH to record build provenance.")
    versions = {"python": platform.python_version()}
    if compiler:
        # Match the registered installation path, not its often-empty PE version.
        if compiler_version(compiler) != tools["inno_setup"]:
            raise RuntimeError(f"Inno Setup {tools['inno_setup']} is required.")
        versions["inno_setup"] = tools["inno_setup"]
    return versions


def digest_files(files: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_digest(root: Path = ROOT) -> str:
    files = [
        p
        for folder in ("app", "assets", "scripts", "installer")
        for p in (root / folder).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    files += [
        p
        for p in root.iterdir()
        if p.is_file()
        and (
            p.suffix in {".ps1", ".spec"}
            or p.name in {"main.py", "toolchain.json"}
            or p.name.startswith("requirements")
        )
    ]
    return digest_files(files, root)


def payload_digest(directory: Path) -> str:
    return digest_files(
        [
            p
            for p in directory.rglob("*")
            if p.is_file() and p.name != "build-manifest.json"
        ],
        directory,
    )


def write_manifest(*, compiler: str | None = None, release: bool = False) -> None:
    tools = preflight(compiler=compiler)
    tools["git"] = subprocess.run(
        ["git", "--version"], check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()
    directory = ROOT / "dist" / "DesktopFocusCompanion"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    manifest = {
        "version": __version__,
        "status": "release-candidate" if release else "UNPUBLISHED local validation",
        "git_commit": commit,
        "workspace_dirty": bool(status),
        "source_sha256": source_digest(),
        "payload_sha256": payload_digest(directory),
        "tools": tools,
        "dependencies": dict(
            sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
            )
        ),
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def verify_manifest(directory: Path, *, expected_source: str | None = None) -> None:
    manifest = json.loads(
        (directory / "build-manifest.json").read_text(encoding="utf-8")
    )
    if manifest["version"] != __version__ or manifest["source_sha256"] != (
        expected_source or source_digest()
    ):
        raise ValueError(
            "Existing EXE is stale: version/source differs. Run a clean application build."
        )
    if manifest["payload_sha256"] != payload_digest(directory):
        raise ValueError(
            "Existing application payload differs from its build manifest."
        )


def version_info():
    # Imported only by PyInstaller, never required by the application at runtime.
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    # preflight restricts the app version to three numeric components (PE format).
    numeric = (*map(int, __version__.split(".")), 0)  # noqa: RUF048
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=numeric,
            prodvers=numeric,
            mask=0x3F,
            flags=0,
            OS=0x40004,
            fileType=1,
            subtype=0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("FileDescription", "Desktop Focus Companion"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", "DesktopFocusCompanion"),
                            StringStruct(
                                "OriginalFilename", "DesktopFocusCompanion.exe"
                            ),
                            StringStruct("ProductName", "Desktop Focus Companion"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "manifest", "verify"))
    parser.add_argument("--compiler")
    parser.add_argument("--tag")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    if args.action == "preflight":
        print(json.dumps(preflight(compiler=args.compiler, tag=args.tag)))
    elif args.action == "manifest":
        write_manifest(compiler=args.compiler, release=args.release)
    else:
        verify_manifest(ROOT / "dist" / "DesktopFocusCompanion")


if __name__ == "__main__":
    main()
