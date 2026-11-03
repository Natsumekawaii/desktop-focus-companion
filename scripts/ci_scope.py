"""Fail closed to Full when the changed-file set cannot be determined."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath


def classify(paths: list[str]) -> str:
    if not paths:
        return "Full"
    for name in paths:
        path = PurePosixPath(name)
        documentation = path.suffix.lower() == ".md"
        image = name.startswith("docs/images/") and path.suffix.lower() in {
            ".png",
            ".jpg",
            ".svg",
            ".webp",
        }
        form = name.startswith(".github/ISSUE_TEMPLATE/") and path.suffix == ".yml"
        if not (documentation or image or form):
            return "Full"
    return "Docs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        if not args.base or set(args.base) == {"0"}:
            raise ValueError("No trustworthy base")
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", "-z", args.base, args.head],
            check=True,
            capture_output=True,
            timeout=30,
        )
        print(classify([p for p in result.stdout.decode("utf-8").split("\0") if p]))
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Full")


if __name__ == "__main__":
    main()
