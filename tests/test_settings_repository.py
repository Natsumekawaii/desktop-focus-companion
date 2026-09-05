"""Tests for robust local settings persistence."""

from pathlib import Path

from app.data.settings_repository import AppSettings, SettingsRepository
from app.focus_mode import FocusMode


def test_missing_or_corrupt_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    repository = SettingsRepository(settings_path)

    assert repository.load() == AppSettings()

    settings_path.write_text("{this is not json", encoding="utf-8")
    assert repository.load() == AppSettings()
    preserved = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(preserved) == 1
    assert preserved[0].read_text(encoding="utf-8") == "{this is not json"


def test_settings_round_trip_and_validate_individual_fields(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    repository = SettingsRepository(settings_path)
    expected = AppSettings(
        pet_x=-120,
        pet_y=450,
        pet_size_percent=135,
        custom_pet_path="pets/custom/pet.png",
        color_theme="dark",
    )

    repository.save(expected)
    assert repository.load() == expected

    settings_path.write_text(
        '{"pet_x": true, "pet_y": 20, "pet_size_percent": 999, '
        '"custom_pet_path": "  ", "always_on_top": "yes", '
        '"notifications_enabled": false, "color_theme": "neon"}',
        encoding="utf-8",
    )
    validated = repository.load()
    assert validated.pet_x is None
    assert validated.pet_y == 20
    assert validated.pet_size_percent == 150
    assert validated.custom_pet_path is None
    assert validated.always_on_top is True
    assert validated.notifications_enabled is False
    assert validated.color_theme == "lavender"


def test_color_theme_defaults_and_persists(tmp_path: Path) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")

    assert repository.load().color_theme == "lavender"
    repository.save(AppSettings(color_theme="charcoal"))

    assert repository.load().color_theme == "charcoal"


def test_focus_timer_defaults_are_backward_compatible_and_persisted(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    repository = SettingsRepository(settings_path)
    settings_path.write_text('{"language":"en-US"}', encoding="utf-8")

    legacy = repository.load()

    assert legacy.default_focus_mode == FocusMode.STOPWATCH.value
    assert legacy.default_focus_target_seconds == 25 * 60
    repository.save(
        AppSettings(
            default_focus_mode=FocusMode.COUNTDOWN.value,
            default_focus_target_seconds=90 * 60,
        )
    )
    restored = repository.load()
    assert restored.default_focus_mode == FocusMode.COUNTDOWN.value
    assert restored.default_focus_target_seconds == 90 * 60


def test_legacy_menu_scheme_is_migrated_to_the_global_color_theme(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"menu_color_scheme":"pink"}', encoding="utf-8")

    loaded = SettingsRepository(settings_path).load()
    saved = settings_path.read_text(encoding="utf-8")

    assert loaded.color_theme == "pink"
    assert '"color_theme": "pink"' in saved
    assert "menu_color_scheme" not in saved


def test_legacy_pet_interaction_fields_are_ignored_and_removed_on_save(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"custom_pet_path":"pets/custom/legacy.gif",'
        '"pet_theme_path":"pets/themes/cat/pet.json",'
        '"animations_enabled":true,"click_reactions_enabled":true,'
        '"hover_info_enabled":true}',
        encoding="utf-8",
    )
    repository = SettingsRepository(settings_path)

    loaded = repository.load()
    repository.save(loaded)
    saved = settings_path.read_text(encoding="utf-8")

    assert loaded.custom_pet_path == "pets/custom/legacy.gif"
    assert "pet_theme_path" not in saved
    assert "animations_enabled" not in saved
    assert "click_reactions_enabled" not in saved
    assert "hover_info_enabled" not in saved


def test_removed_bundled_default_path_is_migrated_without_touching_custom_pets(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    repository = SettingsRepository(settings_path)

    settings_path.write_text(
        '{"custom_pet_path":"C:\\\\Desktop Focus Companion\\\\assets\\\\default_pet\\\\idle.png",'
        '"pet_size_percent":135}',
        encoding="utf-8",
    )
    migrated = repository.load()

    assert migrated.custom_pet_path is None
    assert migrated.pet_size_percent == 135
    assert '"custom_pet_path": null' in settings_path.read_text(encoding="utf-8")

    settings_path.write_text(
        '{"custom_pet_path":"pets/custom/idle.png","pet_size_percent":135}',
        encoding="utf-8",
    )
    custom = repository.load()

    assert custom.custom_pet_path == "pets/custom/idle.png"
