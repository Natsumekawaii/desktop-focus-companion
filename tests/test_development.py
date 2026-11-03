"""Development tooling must never mutate the installed profile or startup entry."""

from pathlib import Path

import pytest

from app.core.paths import ApplicationPaths
from app.integration.single_instance import APPLICATION_MUTEX_NAME
from app.integration.startup_manager import WindowsStartupManager
from scripts.run_dev import development_mutex, development_paths, prepare_profile


def test_development_profile_is_fixed_and_reset_rejects_other_paths(tmp_path: Path):
    paths = development_paths(tmp_path)
    assert paths.data_dir == tmp_path / '.dev-data'
    assert development_mutex(paths) != APPLICATION_MUTEX_NAME
    assert development_mutex(paths) == development_mutex(paths)
    other = tmp_path / 'other'
    other.mkdir()
    marker = other / 'preserve.txt'
    marker.write_text('keep')
    with pytest.raises(ValueError):
        prepare_profile(ApplicationPaths(tmp_path, tmp_path, other), reset=True)
    assert marker.read_text() == 'keep'


def test_development_startup_is_disabled_and_never_reads_registry(tmp_path, monkeypatch):
    import winreg

    def forbidden(*args, **kwargs):
        pytest.fail('Development startup integration accessed the registry')
    monkeypatch.setattr(winreg, 'OpenKey', forbidden)
    monkeypatch.setattr(winreg, 'CreateKey', forbidden)
    startup = WindowsStartupManager(tmp_path, allow_changes=False)
    assert not startup.supported
    assert not startup.is_enabled()
    startup.set_enabled(False)
    with pytest.raises(RuntimeError):
        startup.set_enabled(True)
