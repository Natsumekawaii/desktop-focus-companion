"""Run a disposable source-only development profile, never the installed profile."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from app.application import run_application
from app.core.paths import ApplicationPaths
from app.integration.single_instance import SingleInstanceGuard
from scripts.capture_readme_screenshots import _seed_demo_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def development_paths(root: Path = PROJECT_ROOT) -> ApplicationPaths:
    root = root.resolve(strict=True)
    target = root / '.dev-data'
    # Reject junctions as well as symlinks: resets must never follow a redirect.
    if target.is_symlink() or target.is_junction() or target.resolve().parent != root:
        raise ValueError('Refusing redirected development profile.')
    return ApplicationPaths(root, root / 'assets', target)


def development_mutex(paths: ApplicationPaths) -> str:
    suffix = hashlib.sha256(str(paths.data_dir.resolve()).casefold().encode()).hexdigest()[:16]
    return f'DesktopFocusCompanion-Development-{suffix}'


def prepare_profile(paths: ApplicationPaths, *, reset: bool = False) -> None:
    expected = development_paths(paths.project_root).data_dir
    if paths.data_dir != expected:
        raise ValueError('Only the dedicated development profile can be reset.')
    # Keep the preparation lock OUTSIDE the directory being reset, so no other
    # launcher can enter between reset, seeding and application startup.
    if reset and expected.exists():
        shutil.rmtree(expected)
    if not expected.exists():
        staging = expected.with_name('.dev-data-initializing')
        if staging.exists():
            raise RuntimeError('Incomplete demo initialization exists; inspect .dev-data-initializing.')
        staging.mkdir()
        _seed_demo_profile(ApplicationPaths(paths.project_root, paths.assets_dir, staging), 'zh-CN')
        staging.rename(expected)


def main() -> int:
    if getattr(sys, 'frozen', False):
        raise RuntimeError('The development launcher is source-only.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset-demo', action='store_true')
    arguments = parser.parse_args()
    paths = development_paths()
    mutex = development_mutex(paths)
    with SingleInstanceGuard(paths.project_root / '.dev-data.lock', mutex_name=mutex):
        prepare_profile(paths, reset=arguments.reset_demo)
        return run_application(['desktop-focus-companion-development'], paths=paths, development=True)


if __name__ == '__main__':
    raise SystemExit(main())
