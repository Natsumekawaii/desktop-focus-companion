"""Public-repository documentation and release-contract checks."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from app import __version__
from app.core.theme import COLOR_THEMES
from scripts.capture_readme_screenshots import (
    THEME_LABEL_HEIGHT,
    THEME_PREVIEW_HEIGHT,
    THEME_PREVIEW_WIDTH,
    THEME_SHEET_COLUMNS,
    THEME_SHEET_GAP,
    THEME_SHEET_MARGIN,
    _theme_contact_sheet,
)

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
THEME_SHEET_SIZE = (1332, 708)
BILINGUAL_MARKDOWN_PAIRS = (
    (Path("README.md"), Path("README.zh-CN.md")),
    (Path("CHANGELOG.md"), Path("CHANGELOG.zh-CN.md")),
    (Path("CONTRIBUTING.md"), Path("CONTRIBUTING.zh-CN.md")),
    (Path("SECURITY.md"), Path("SECURITY.zh-CN.md")),
    (Path("docs/architecture.md"), Path("docs/architecture.zh-CN.md")),
    (Path("docs/data-safety.md"), Path("docs/data-safety.zh-CN.md")),
    (Path("docs/database.md"), Path("docs/database.zh-CN.md")),
    (Path("docs/i18n.md"), Path("docs/i18n.zh-CN.md")),
    (Path("docs/verification.md"), Path("docs/verification.zh-CN.md")),
    (
        Path(f".github/release-notes/v{__version__}.md"),
        Path(f".github/release-notes/v{__version__}.zh-CN.md"),
    ),
)
LANGUAGE_SECTION_MARKERS = {
    "README.md": ("## Quick start", "## 快速开始"),
    "CHANGELOG.md": ("## [Unreleased]", "## [未发布]"),
    "CONTRIBUTING.md": ("## Development workflow", "## 开发流程"),
    "SECURITY.md": ("## Supported versions", "## 支持的版本"),
    "architecture.md": ("## Composition Root", "## 组合根"),
    "data-safety.md": ("## Immediate persistence", "## 即时持久化"),
    "database.md": ("## Other retained tables", "## 其他保留表"),
    "i18n.md": ("## Implementation", "## 实现方案"),
    "verification.md": ("## 1. Quality gate", "## 1. 质量检查"),
    f"v{__version__}.md": ("## Downloads", "## 下载"),
}
PULL_REQUEST_LANGUAGE_SWITCH = (
    "[English](https://github.com/Natsumekawaii/desktop-focus-companion/blob/"
    "main/.github/PULL_REQUEST_TEMPLATE.md) | "
    "[简体中文](https://github.com/Natsumekawaii/desktop-focus-companion/"
    "blob/main/.github/PULL_REQUEST_TEMPLATE/pull_request.zh-CN.md)"
)


def _read(path: Path) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _png_size(contents: bytes) -> tuple[int, int]:
    assert contents.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", contents[16:24])


def _language_switch(english: Path, chinese: Path) -> str:
    return f"[English]({english.name}) | [简体中文]({chinese.name})"


def _form_contract(text: str) -> tuple[tuple[str, ...], ...]:
    labels_match = re.search(r"^labels:\s*(.+)$", text, re.MULTILINE)
    assert labels_match is not None
    return (
        tuple(re.findall(r"^\s{2}- type:\s*([\w-]+)$", text, re.MULTILINE)),
        tuple(re.findall(r"^\s{4}id:\s*([\w-]+)$", text, re.MULTILINE)),
        tuple(re.findall(r"^\s+required:\s*(true|false)$", text, re.MULTILINE)),
        (labels_match.group(1),),
    )


def test_bilingual_markdown_pairs_are_complete_and_language_specific() -> None:
    for english_path, chinese_path in BILINGUAL_MARKDOWN_PAIRS:
        english = _read(english_path)
        chinese = _read(chinese_path)
        switch = _language_switch(english_path, chinese_path)

        assert english.splitlines()[0] == switch
        assert chinese.splitlines()[0] == switch
        assert len(re.findall(r"^## ", english, re.MULTILINE)) == len(
            re.findall(r"^## ", chinese, re.MULTILINE)
        )

        english_marker, chinese_marker = LANGUAGE_SECTION_MARKERS[english_path.name]
        assert english_marker in english
        assert chinese_marker not in english
        assert chinese_marker in chinese
        assert english_marker not in chinese


def test_all_public_markdown_uses_the_bilingual_pair_convention() -> None:
    paired_paths = {
        path
        for pair in BILINGUAL_MARKDOWN_PAIRS
        for path in pair
    }
    localizable_paths = {
        path.relative_to(PROJECT_ROOT)
        for path in (
            *PROJECT_ROOT.glob("*.md"),
            *(PROJECT_ROOT / "docs").glob("*.md"),
            *(PROJECT_ROOT / ".github" / "release-notes").glob("*.md"),
        )
    }

    assert localizable_paths == paired_paths


def test_readmes_use_language_specific_screenshots() -> None:
    for language, path in (
        ("en", Path("README.md")),
        ("zh", Path("README.zh-CN.md")),
    ):
        readme = _read(path)
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


def test_readme_product_tour_uses_the_compact_aligned_order() -> None:
    for path, titles, language in (
        (
            Path("README.md"),
            (
                "Focus panel",
                "Focus Item management",
                "Analytics",
                "Monthly calendar",
                "Focus history",
                "True-time timeline",
            ),
            "en",
        ),
        (
            Path("README.zh-CN.md"),
            ("专注面板", "项目管理", "数据分析", "月度日历", "专注历史", "真实时间轴"),
            "zh",
        ),
    ):
        readme = _read(path)
        table = re.search(r"<table>(.*?)</table>", readme, re.DOTALL)
        assert table is not None
        cells = re.findall(r"<td[^>]*>(.*?)</td>", table.group(1), re.DOTALL)
        assert len(cells) == 6
        assert tuple(re.search(r"<strong>(.*?)</strong>", cell).group(1) for cell in cells) == titles
        assert tuple(
            re.search(rf'docs/images/{language}/([a-z-]+\.png)', cell).group(1)
            for cell in cells
        ) == (
            "focus-panel.png",
            "focus-items.png",
            "analytics.png",
            "monthly.png",
            "history.png",
            "timeline.png",
        )
        assert 'height="420"' in cells[0]
        assert 'height="420"' in cells[1]


def test_theme_contact_sheets_are_compact_landscape_images() -> None:
    for language, names in (
        ("en", ("Default", "Lavender", "Pink", "Blue", "Dark", "Charcoal")),
        ("zh", ("默认", "浅紫色", "浅粉色", "浅蓝色", "深色", "炭黑")),
    ):
        path = Path("docs") / "images" / language / "themes.png"
        contents = (PROJECT_ROOT / path).read_bytes()
        assert _png_size(contents) == THEME_SHEET_SIZE
        readme = _read(Path("README.md" if language == "en" else "README.zh-CN.md"))
        theme_image = re.search(
            rf'<a href="{re.escape(path.as_posix())}"><img src="{re.escape(path.as_posix())}" alt="([^"]+)"></a>',
            readme,
        )
        assert theme_image is not None
        alt_text = theme_image.group(1)
        positions = tuple(alt_text.index(name) for name in names)
        assert positions == tuple(sorted(positions))


def test_theme_contact_sheet_preserves_the_stable_three_by_two_order(
    qt_application,
) -> None:
    colors = ("#d9534f", "#8f63b8", "#cc5b86", "#4286b4", "#77518f", "#69717d")
    previews: dict[str, QImage] = {}
    for theme_name, color in zip(COLOR_THEMES, colors, strict=True):
        preview = QImage(16, 12, QImage.Format.Format_RGB32)
        preview.fill(QColor(color))
        previews[theme_name] = preview

    sheet = _theme_contact_sheet(previews)

    assert (sheet.width(), sheet.height()) == THEME_SHEET_SIZE
    assert len(previews) == 6
    for index, color in enumerate(colors):
        row, column = divmod(index, THEME_SHEET_COLUMNS)
        x = (
            THEME_SHEET_MARGIN
            + column * (THEME_PREVIEW_WIDTH + THEME_SHEET_GAP)
            + THEME_PREVIEW_WIDTH // 2
        )
        y = (
            THEME_SHEET_MARGIN
            + row
            * (THEME_LABEL_HEIGHT + THEME_PREVIEW_HEIGHT + THEME_SHEET_GAP)
            + THEME_LABEL_HEIGHT
            + THEME_PREVIEW_HEIGHT // 2
        )
        assert sheet.pixelColor(x, y).name() == color


def test_public_markdown_relative_links_resolve() -> None:
    public_markdown = {
        path
        for pair in BILINGUAL_MARKDOWN_PAIRS
        for path in pair
    }
    public_markdown.update(
        {
            Path(".github/PULL_REQUEST_TEMPLATE.md"),
            Path(".github/PULL_REQUEST_TEMPLATE/pull_request.zh-CN.md"),
        }
    )

    for relative_path in public_markdown:
        document = _read(relative_path)
        targets = re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", document)
        relative_targets = {
            target.split("#", maxsplit=1)[0]
            for target in targets
            if not target.startswith(("http://", "https://", "#"))
        }
        for target in relative_targets:
            resolved = PROJECT_ROOT / relative_path.parent / target
            assert resolved.exists(), (
                f"{relative_path} links to missing path {target!r}"
            )


def test_pull_request_templates_are_separate_and_english_is_default() -> None:
    english = _read(Path(".github/PULL_REQUEST_TEMPLATE.md"))
    chinese = _read(
        Path(".github/PULL_REQUEST_TEMPLATE/pull_request.zh-CN.md")
    )

    assert english.splitlines()[0] == PULL_REQUEST_LANGUAGE_SWITCH
    assert chinese.splitlines()[0] == PULL_REQUEST_LANGUAGE_SWITCH
    assert "## Summary" in english
    assert "## 变更总结" not in english
    assert "## 变更总结" in chinese
    assert "## Summary" not in chinese


def test_issue_forms_are_separate_and_have_matching_contracts() -> None:
    issue_root = Path(".github/ISSUE_TEMPLATE")
    for stem in ("bug_report", "feature_request"):
        english = _read(issue_root / f"{stem}.yml")
        chinese = _read(issue_root / f"{stem}.zh-CN.yml")

        assert _form_contract(english) == _form_contract(chinese)
        assert f"template={stem}.yml" in english
        assert f"template={stem}.zh-CN.yml" in english
        assert f"template={stem}.yml" in chinese
        assert f"template={stem}.zh-CN.yml" in chinese
        assert not re.search(r"^(?:name|description):.* / ", english, re.MULTILINE)
        assert not re.search(r"^(?:name|description):.* / ", chinese, re.MULTILINE)

    config = _read(issue_root / "config.yml")
    assert "Security report\n" in config
    assert "安全问题\n" in config
    assert "Questions and ideas\n" in config
    assert "问答与讨论\n" in config
    assert " / " not in config


def test_public_metadata_uses_one_release_version() -> None:
    installer = _read(Path("installer/DesktopFocusCompanion.iss"))
    for path in (
        Path("CHANGELOG.md"),
        Path("CHANGELOG.zh-CN.md"),
        Path(f".github/release-notes/v{__version__}.md"),
        Path(f".github/release-notes/v{__version__}.zh-CN.md"),
    ):
        assert __version__ in _read(path)
    assert f'#define MyAppVersion "{__version__}"' in installer


def test_release_workflow_requires_and_links_both_note_languages() -> None:
    workflow = _read(Path(".github/workflows/release.yml"))

    assert "$tag.md" in workflow
    assert "$tag.zh-CN.md" in workflow
    assert "English release notes were not found" in workflow
    assert "Simplified Chinese release notes were not found" in workflow
    assert "${{ github.sha }}" in workflow
    assert "$publishedLines = @($languageLinks, '') + $englishBody" in workflow
    assert "gh release edit" in workflow
    assert "--generate-notes" not in workflow


def test_public_files_do_not_contain_private_workspace_markers() -> None:
    public_files = [
        *PROJECT_ROOT.glob("*.md"),
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
