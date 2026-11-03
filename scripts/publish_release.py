"""Create a release once; an existing release is immutable in this workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from scripts.build_support import ROOT, preflight


def assert_identical_assets(local: dict[str, str], remote: dict[str, str]) -> None:
    if local != remote:
        raise ValueError(
            "Release already exists with missing/different assets. Refusing to overwrite it."
        )


def notes_body(tag: str, repository: str, revision: str) -> str:
    english = ROOT / ".github" / "release-notes" / f"{tag}.md"
    chinese = ROOT / ".github" / "release-notes" / f"{tag}.zh-CN.md"
    if not english.is_file() or not chinese.is_file():
        raise ValueError(
            "Both English and Simplified Chinese release notes are required."
        )
    body = english.read_text(encoding="utf-8").splitlines()
    if body and body[0].startswith("[English]"):
        body = body[1:]
    links = (
        f"[English](https://github.com/{repository}/releases/tag/{tag}) | "
        f"[简体中文](https://github.com/{repository}/blob/{revision}/.github/release-notes/{tag}.zh-CN.md)"
    )
    return links + "\n\n" + "\n".join(body).lstrip()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def publish(tag: str, repository: str, revision: str, assets: list[Path]) -> None:
    preflight(tag=tag)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not re.fullmatch(
        r"[0-9a-f]{40}", revision
    ):
        raise ValueError("Invalid release repository/revision.")
    body = notes_body(tag, repository, revision)
    local = {path.name: file_hash(path) for path in assets}
    if len(local) != len(assets):
        raise ValueError("Duplicate asset names.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/tags/{tag}",
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            existing = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        existing = None
    with tempfile.TemporaryDirectory(prefix="focus-release-") as temporary:
        directory = Path(temporary)
        if existing is not None:
            if {a["name"] for a in existing["assets"]} != set(local):
                raise ValueError(
                    "Existing release asset set differs; no assets were changed."
                )
            subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    repository,
                    "--dir",
                    str(directory),
                ],
                check=True,
                timeout=180,
            )
            assert_identical_assets(
                local, {p.name: file_hash(p) for p in directory.iterdir()}
            )
            print("Release assets are identical; nothing changed.")
            return
        notes = directory / "release-notes.md"
        notes.write_text(body, encoding="utf-8")
        subprocess.run(
            [
                "gh",
                "release",
                "create",
                tag,
                *map(str, assets),
                "--repo",
                repository,
                "--verify-tag",
                "--title",
                f"Desktop Focus Companion {tag}",
                "--notes-file",
                str(notes),
            ],
            check=True,
            timeout=180,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("repository")
    parser.add_argument("revision")
    parser.add_argument("assets", nargs="+", type=Path)
    args = parser.parse_args()
    publish(args.tag, args.repository, args.revision, args.assets)


if __name__ == "__main__":
    main()
