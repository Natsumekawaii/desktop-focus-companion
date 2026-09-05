"""Shared pytest configuration."""

import os

import pytest

# Let Qt tests run without requiring an attached display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_application():
    """Provide one QApplication for all Qt object tests."""
    from app.application import create_application

    return create_application(["desktop-focus-companion-test"])
