"""Shared pytest configuration."""

import gc
import os
from time import monotonic

import pytest

# Let Qt tests run without requiring an attached display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_application():
    """Provide one QApplication for all Qt object tests."""
    from app.application import create_application

    return create_application(["desktop-focus-companion-test"])


@pytest.fixture
def qt_wait_until(qt_application):
    """Bounded event-loop wait for the few tests exercising real animation time."""
    from PySide6.QtTest import QTest
    def wait(predicate, timeout_ms=1000):
        deadline = monotonic() + timeout_ms / 1000
        while not predicate():
            if monotonic() >= deadline:
                pytest.fail(f'Qt condition was not reached within {timeout_ms}ms')
            QTest.qWait(5)
        qt_application.processEvents()
    return wait


@pytest.fixture(autouse=True)
def qt_resource_scope(qt_application, monkeypatch):
    """Own each test's Qt objects without changing production close semantics."""
    from dataclasses import fields

    from PySide6.QtCore import (
        QAbstractAnimation,
        QCoreApplication,
        QEvent,
        QObject,
        QTimer,
    )
    from PySide6.QtWidgets import QSystemTrayIcon
    from shiboken6 import isValid

    from app.application import ApplicationRuntime
    from app.core.theme import get_theme_manager
    from app.i18n import get_localization
    from app.ui.info_bubble import get_animated_tooltip_manager

    theme = get_theme_manager()
    localization = get_localization()
    initial_theme, initial_language = theme.theme_name, localization.language
    initial_quit_policy = qt_application.quitOnLastWindowClosed()
    baseline = set(qt_application.allWidgets())
    owned: list[QObject] = []
    original_init = ApplicationRuntime.__init__

    def tracked_init(runtime, *args, **kwargs):
        original_init(runtime, *args, **kwargs)
        owned.extend(
            value for field in fields(runtime)
            if isinstance(value := getattr(runtime, field.name), QObject)
        )

    monkeypatch.setattr(ApplicationRuntime, '__init__', tracked_init)
    yield
    theme._transition.finish_all()
    tooltips = get_animated_tooltip_manager()
    if tooltips is not None:
        tooltips.hide_immediately()
    added = set(qt_application.allWidgets()) - baseline
    roots = [w for w in added if w.parentWidget() not in added]
    for obj in [*owned, *roots]:
        if not isValid(obj):
            continue
        for timer in obj.findChildren(QTimer):
            timer.stop()
        for animation in obj.findChildren(QAbstractAnimation):
            animation.stop()
        for tray in obj.findChildren(QSystemTrayIcon):
            tray.hide()
        obj.deleteLater()
    # Clear Python cycles as well as Qt's deferred-delete queue. Shared app-level
    # tooltip/theme objects were captured in the baseline and are never deleted.
    for _ in range(2):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()
    localization.set_language(initial_language)
    theme.set_theme(initial_theme)
    theme._transition.finish_all()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_application.setQuitOnLastWindowClosed(initial_quit_policy)
    remaining = set(qt_application.allWidgets()) - baseline
    assert not remaining, f'{len(remaining)} test-owned Qt widgets survived teardown'
