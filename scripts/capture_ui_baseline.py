"""Capture deterministic pre/post refactor images without touching user data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QScrollArea

from app.application import build_runtime, create_application
from app.core.paths import ApplicationPaths
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.i18n import get_localization
from app.ui.dashboard import DashboardPage
from scripts.capture_readme_screenshots import _capture, _seed_demo_profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    application = create_application(['visual-baseline'])
    root = Path(__file__).resolve().parents[1]
    hashes = {}
    with TemporaryDirectory(prefix='focus-visual-') as temp:
        paths = ApplicationPaths(root, root / 'assets', Path(temp))
        _seed_demo_profile(paths, 'en-US')
        runtime = build_runtime(paths, development=True)
        for language in ('en-US', 'zh-CN'):
            get_localization().set_language(language)
            runtime.dashboard_controller.refresh()
            for theme in COLOR_THEMES:
                get_theme_manager().set_theme(theme)
                hashes[f'{language}/{theme}'] = hashlib.sha256(application.styleSheet().encode()).hexdigest()
                for width in (760, 1024):
                    for page in DashboardPage:
                        window = runtime.dashboard_window
                        window.set_current_page(page)
                        for scroll in window.findChildren(QScrollArea):
                            scroll.verticalScrollBar().setValue(0)
                        _capture(application, window, output / f'{language}-{theme}-{width}-{page.name}.png', width, 752)
                    _capture(application, runtime.settings_dialog, output / f'{language}-{theme}-{width}-settings.png', width, 680)
                _capture(application, runtime.quick_panel, output / f'{language}-{theme}-focus.png', 380, 620)
        runtime.tray_controller.tray_icon.hide()
        for window in application.topLevelWidgets():
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    (output / 'qss.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
