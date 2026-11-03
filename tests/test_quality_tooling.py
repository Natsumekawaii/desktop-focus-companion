"""Contracts for dependency boundaries and fast, reproducible quality gates."""

import re
from importlib.metadata import version
from pathlib import Path

from scripts.build_support import pinned_dependencies
from scripts.ci_scope import classify
from scripts.quality import commands

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dependencies_are_separate_pinned_and_match_installed_versions():
    runtime = (PROJECT_ROOT / "requirements.txt").read_text()
    dev = (PROJECT_ROOT / "requirements-dev.txt").read_text()
    build = (PROJECT_ROOT / "requirements-build.txt").read_text()
    assert set(re.findall(r"^([\w.-]+)==", runtime, re.MULTILINE)) == {
        "PySide6",
        "tzdata",
    }
    assert "-r requirements.txt" in dev and "-r requirements.txt" in build
    assert set(re.findall(r"^([\w.-]+)==", dev, re.MULTILINE)) == {
        "pytest",
        "ruff",
        "mypy",
    }
    assert set(re.findall(r"^([\w.-]+)==", build, re.MULTILINE)) == {"PyInstaller"}
    for name, expected in pinned_dependencies(build=False).items():
        assert version(name) == expected


def test_quality_modes_and_explicit_targets():
    full = commands("Full", "All", [])
    assert [name for name, _ in full] == ["Ruff", "Mypy", "Tests"]
    assert not any(s.startswith("tests/") for s in full[-1][1])
    assert "tests/test_public_repository.py" in commands("Docs", "Tests", [])[0][1]
    assert "tests/test_database.py" in commands("Fast", "Tests", [])[0][1]
    assert (
        commands("Full", "Tests", ["tests/test_i18n.py"])[0][1][-1]
        == "tests/test_i18n.py"
    )
    assert "--durations=25" in full[-1][1]
    assert any(s.startswith("--junitxml=") for s in full[-1][1])


def test_ci_scope_never_skips_required_gate_and_defaults_to_full():
    assert (
        classify(
            [
                "README.md",
                "docs/images/en/themes.png",
                ".github/ISSUE_TEMPLATE/bug_report.yml",
            ]
        )
        == "Docs"
    )
    for paths in (
        [],
        ["requirements.txt"],
        ["app/application.py"],
        [".github/workflows/ci.yml"],
        ["build.ps1"],
        ["README.md", "unknown.file"],
        ["docs/data.sqlite3"],
    ):
        assert classify(paths) == "Full"
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text()
    assert "name: Windows quality gate" in workflow
    assert "paths-ignore:" not in workflow
    assert all(f"name: {name}" in workflow for name in ("Ruff", "mypy", "pytest"))
    assert "requirements.txt" in workflow and "requirements-dev.txt" in workflow
    assert "if: always()" in workflow
