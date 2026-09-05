"""Public-repository documentation and release-contract checks."""

from __future__ import annotations

import re
from pathlib import Path

from app import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_NAMES = {
    "analytics.png",
    "focus-items.png",
    "focus-panel.png",
    "history.png",
    "monthly.png",
    "overview.png",
    "themes.png",
    "timeline.png",
}
LANGUAGE_SWITCH = "[English](README.md) | [简体中文](README.zh-CN.md)"


def test_readme_has_language_switch_and_valid_local_images() -> None:
    readmes = {
        "en": (PROJECT_ROOT / "README.md").read_text(encoding="utf-8"),
        "zh": (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
    }

    for language, readme in readmes.items():
        assert readme.splitlines()[0] == LANGUAGE_SWITCH
        assert "GITHUB_OWNER" not in readme

        image_paths = set(
            re.findall(r"docs/images/(?:zh|en)/[a-z-]+\.png", readme)
        )
        assert image_paths == {
            f"docs/images/{language}/{name}" for name in SCREENSHOT_NAMES
        }
        for image_path in image_paths:
            contents = (PROJECT_ROOT / image_path).read_bytes()
            assert contents.startswith(b"\x89PNG\r\n\x1a\n")
            assert len(contents) > 10_000

    assert "## Quick start" in readmes["en"]
    assert "## 快速开始" not in readmes["en"]
    assert "## 快速开始" in readmes["zh"]
    assert "## Quick start" not in readmes["zh"]


def test_readme_relative_links_resolve() -> None:
    for filename in ("README.md", "README.zh-CN.md"):
        readme = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        targets = re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", readme)
        relative_targets = {
            target.split("#", maxsplit=1)[0]
            for target in targets
            if not target.startswith(("http://", "https://", "#"))
        }

        for target in relative_targets:
            assert (PROJECT_ROOT / target).exists(), (
                f"{filename} links to missing path {target!r}"
            )


def test_public_metadata_uses_one_release_version() -> None:
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / ".github" / "release-notes" / f"v{__version__}.md"
    ).read_text(encoding="utf-8")
    installer = (
        PROJECT_ROOT / "installer" / "DesktopFocusCompanion.iss"
    ).read_text(encoding="utf-8")

    assert f"## [{__version__}]" in changelog
    assert f"Desktop Focus Companion {__version__}" in release_notes
    assert f'#define MyAppVersion "{__version__}"' in installer


def test_public_files_do_not_contain_private_workspace_markers() -> None:
    public_files = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "README.zh-CN.md",
        PROJECT_ROOT / "CHANGELOG.md",
        PROJECT_ROOT / "CONTRIBUTING.md",
        PROJECT_ROOT / "SECURITY.md",
        *(PROJECT_ROOT / "docs").glob("*.md"),
        *(PROJECT_ROOT / ".github").rglob("*.md"),
        *(PROJECT_ROOT / ".github").rglob("*.yml"),
    ]
    forbidden_patterns = (
        re.compile(r"[A-Za-z]:\\(?:Users|Projects)\\", re.IGNORECASE),
        re.compile(r"@local\.invalid\b", re.IGNORECASE),
        re.compile("GITHUB_" "OWNER"),
        re.compile("Local Data " "Reset"),
    )

    for path in public_files:
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert pattern.search(text) is None, (
                f"{path.relative_to(PROJECT_ROOT)} contains {pattern.pattern!r}"
            )
