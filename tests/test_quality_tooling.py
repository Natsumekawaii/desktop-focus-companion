"""Release-engineering contracts for reproducible local checks."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _requirements(name: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in (PROJECT_ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_runtime_development_and_build_dependencies_are_separate_and_pinned() -> None:
    assert _requirements("requirements.txt") == ("PySide6==6.11.1",)
    assert _requirements("requirements-dev.txt") == (
        "-r requirements.txt",
        "pytest==9.1.1",
        "ruff==0.16.3",
        "mypy==1.20.2",
    )
    assert _requirements("requirements-build.txt") == (
        "-r requirements.txt",
        "PyInstaller==6.22.0",
    )


def test_quality_script_runs_static_checks_before_the_complete_test_suite() -> None:
    script = (PROJECT_ROOT / "quality.ps1").read_text(encoding="utf-8")

    ruff = script.index("-m ruff check .")
    mypy = script.index("-m mypy app main.py")
    pytest = script.index("-m pytest -q")
    assert ruff < mypy < pytest
    assert script.count("if ($LASTEXITCODE -ne 0)") == 3
