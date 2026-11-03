"""Read-only, timed quality gates; generated reports are not version-controlled."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
CORE_TESTS = (
    "test_database",
    "test_repositories",
    "test_statistics_service",
    "test_focus_domain",
    "test_focus_session_manager",
    "test_active_session_recovery",
    "test_record_hardening",
    "test_runtime_hardening",
    "test_recovery_hardening",
    "test_development",
    "test_gamification",
    "test_dashboard_optimization",
    "test_quality_tooling",
    "test_build_hardening",
)


def commands(mode: str, stage: str, tests: list[str]) -> list[tuple[str, list[str]]]:
    selected = tests or (
        ["tests/test_public_repository.py"]
        if mode == "Docs"
        else [f"tests/{name}.py" for name in CORE_TESTS]
        if mode == "Fast"
        else []
    )
    gates = [
        ("Ruff", ["-m", "ruff", "check", "."]),
        ("Mypy", ["-m", "mypy", "app", "main.py"]),
        (
            "Tests",
            [
                "-m",
                "pytest",
                "-q",
                "--durations=25",
                "--junitxml=artifacts/quality/junit.xml",
                *selected,
            ],
        ),
    ]
    return [gate for gate in gates if stage in ("All", gate[0])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("Full", "Fast", "Docs"), default="Full")
    parser.add_argument(
        "--stage", choices=("All", "Ruff", "Mypy", "Tests"), default="All"
    )
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args()
    reports = ROOT / "artifacts" / "quality"
    reports.mkdir(parents=True, exist_ok=True)
    for name, command in commands(args.mode, args.stage, args.tests):
        started = perf_counter()
        with (
            (reports / f"{name.lower()}.log").open("w", encoding="utf-8") as log,
            subprocess.Popen(
                [sys.executable, *command],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            ) as process,
        ):
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="")
                log.write(line)
            result = process.wait()
        elapsed = perf_counter() - started
        (reports / f"{name.lower()}.json").write_text(
            json.dumps(
                {
                    "stage": name,
                    "mode": args.mode,
                    "seconds": elapsed,
                    "exit_code": result,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{name}: {elapsed:.2f}s, exit {result}", flush=True)
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
