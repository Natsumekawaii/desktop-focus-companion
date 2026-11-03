"""Private SettingsDialog control construction; behavior stays in the public window."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.theme import COLOR_THEMES, get_theme_manager
from app.data.settings_repository import MAX_PET_SIZE_PERCENT, MIN_PET_SIZE_PERCENT
from app.focus_mode import FocusMode
from app.i18n import SUPPORTED_LANGUAGES, get_localization
from app.ui.components import DurationPicker
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity


class _SettingsDialogBuilders:
    # Construction calls hooks supplied by the concrete Qt window. This bridge
    # is type-checking-only; it does not change runtime attribute lookup.
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...

    def _build_companion_controls(self) -> tuple[QWidget, QWidget]:
        self._current_pet_label = QLabel()
        self._current_pet_label.setWordWrap(True)
        self._size_value_label = QLabel()
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setObjectName("secondary")

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(MIN_PET_SIZE_PERCENT, MAX_PET_SIZE_PERCENT)
        self._size_slider.setSingleStep(5)
        self._size_slider.setPageStep(10)
        self._size_slider.valueChanged.connect(self._on_size_value_changed)

        self._import_button = self._button("settings.change_pet_image", self._choose_image)
        self._default_button = self._button("settings.use_default", self.use_default_requested)
        image_buttons = QVBoxLayout()
        image_buttons.setContentsMargins(0, 0, 0, 0)
        image_buttons.setSpacing(8)
        image_buttons.addWidget(self._import_button)
        image_buttons.addWidget(self._default_button)
        image_controls = QWidget()
        image_controls.setLayout(image_buttons)

        size_row = QHBoxLayout()
        size_row.addWidget(self._size_slider, stretch=1)
        size_row.addWidget(self._size_value_label)
        size_controls = QWidget()
        size_controls.setLayout(size_row)

        return image_controls, size_controls

    def _build_page_stack(self, image_controls: QWidget, size_controls: QWidget) -> None:
        from app.ui.settings_dialog import _SettingsPageStack
        self._tabs = _SettingsPageStack()
        self._tabs.setObjectName("settingsPages")
        self._pages = self._tabs
        self._appearance_tab, self._appearance_form = self._form_tab()
        self._companion_tab, self._companion_form = self._form_tab()
        self._timer_tab, self._timer_form = self._form_tab()
        self._data_tab, self._data_form = self._form_tab()
        self._about_tab, self._about_form = self._form_tab()
        for page in (
            self._appearance_tab,
            self._companion_tab,
            self._timer_tab,
            self._data_tab,
            self._about_tab,
        ):
            self._tabs.addPage(page)

        self._nav_group = QButtonGroup(cast(QWidget, self))
        self._nav_group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        for index in range(self._tabs.count()):
            button = QPushButton()
            button.setObjectName("sidebarNavButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setMinimumHeight(42)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self._select_page(page_index)
            )
            self._nav_group.addButton(button, index)
            self._nav_buttons.append(button)
        self._nav_buttons[0].setChecked(True)
        self._tabs.currentChanged.connect(self._on_page_changed)

        self._page_title = QLabel()
        self._page_title.setObjectName("pageTitle")
        self._form = self._timer_form
        self._refresh_icons()
        get_theme_manager().theme_changed.connect(self._refresh_icons)
        self._add_row(self._companion_form, "settings.current_pet", self._current_pet_label)
        self._add_row(self._companion_form, "settings.pet_image", image_controls)
        self._add_row(self._companion_form, "settings.pet_size", size_controls)

    def _build_appearance_page(self) -> None:
        from app.ui.settings_dialog import _theme_swatch_icon
        self._app_icon_preview = QLabel()
        self._app_icon_preview.setFixedSize(56, 56)
        self._app_icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._current_app_icon_label = QLabel()
        self._current_app_icon_label.setWordWrap(True)
        self._current_app_icon_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        current_app_icon_layout = QHBoxLayout()
        current_app_icon_layout.addWidget(self._app_icon_preview)
        current_app_icon_layout.addWidget(self._current_app_icon_label, stretch=1)
        current_app_icon_controls = QWidget()
        current_app_icon_controls.setLayout(current_app_icon_layout)
        self._change_app_icon_button = self._button(
            "settings.change_app_icon", self._choose_app_icon
        )
        self._default_app_icon_button = self._button(
            "settings.reset_app_icon", self.use_default_app_icon_requested
        )
        app_icon_buttons = QVBoxLayout()
        app_icon_buttons.setContentsMargins(0, 0, 0, 0)
        app_icon_buttons.setSpacing(8)
        app_icon_buttons.addWidget(self._change_app_icon_button)
        app_icon_buttons.addWidget(self._default_app_icon_button)
        app_icon_button_controls = QWidget()
        app_icon_button_controls.setLayout(app_icon_buttons)
        self._add_row(
            self._appearance_form, "settings.current_app_icon", current_app_icon_controls
        )
        self._add_row(
            self._appearance_form, "settings.application_icon", app_icon_button_controls
        )

        self._language_combo = RoundedComboBox(density=SelectorDensity.COMPACT)
        for language in SUPPORTED_LANGUAGES:
            self._language_combo.addItem(language.native_name, language.code)
        initial_language_index = self._language_combo.findData(get_localization().language)
        self._language_combo.setCurrentIndex(max(0, initial_language_index))
        self._language_combo.currentIndexChanged.connect(self._on_language_selected)
        self._add_row(self._appearance_form, "settings.language", self._language_combo)

        self._color_theme_combo = RoundedComboBox(density=SelectorDensity.COMPACT)
        for theme_name in COLOR_THEMES:
            self._color_theme_combo.addItem("", theme_name)
        self._color_theme_combo.currentIndexChanged.connect(self._on_color_theme_selected)
        self._color_theme_combo.hide()
        theme_picker = QWidget()
        theme_picker_layout = QHBoxLayout(theme_picker)
        theme_picker_layout.setContentsMargins(0, 0, 0, 0)
        theme_picker_layout.setSpacing(8)
        self._theme_button_group = QButtonGroup(cast(QWidget, self))
        self._theme_button_group.setExclusive(True)
        self._theme_buttons: list[QPushButton] = []
        for index, theme_name in enumerate(COLOR_THEMES):
            button = QPushButton()
            button.setObjectName("themeSwatch")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedSize(46, 46)
            button.setIcon(_theme_swatch_icon(theme_name))
            button.setIconSize(QSize(34, 34))
            button.clicked.connect(
                lambda _checked=False, target=index: self._color_theme_combo.setCurrentIndex(target)
            )
            self._theme_button_group.addButton(button, index)
            self._theme_buttons.append(button)
            theme_picker_layout.addWidget(button)
        theme_picker_layout.addStretch()
        theme_picker_layout.addWidget(self._color_theme_combo)
        self._add_row(
            self._appearance_form, "settings.color_theme", theme_picker
        )

    def _build_timer_page(self) -> None:
        self._daily_goal_minutes = DurationPicker(15, 24 * 60)
        self._weekly_goal_minutes = DurationPicker(15, 25 * 60)
        self._streak_minutes = DurationPicker(5, 24 * 60)
        self._daily_goal_minutes.valueChanged.connect(
            self._emit_focus_goal_preferences
        )
        self._weekly_goal_minutes.valueChanged.connect(
            self._emit_focus_goal_preferences
        )
        self._streak_minutes.valueChanged.connect(
            self._emit_focus_goal_preferences
        )
        self._add_row(self._timer_form, "settings.daily_goal", self._daily_goal_minutes)
        self._add_row(self._timer_form, "settings.weekly_goal", self._weekly_goal_minutes)
        self._add_row(self._timer_form, "settings.minimum_streak", self._streak_minutes)

        self._default_focus_mode = RoundedComboBox(
            density=SelectorDensity.COMPACT
        )
        self._default_focus_mode.addItem("", FocusMode.STOPWATCH.value)
        self._default_focus_mode.addItem("", FocusMode.COUNTDOWN.value)
        self._default_focus_target_minutes = DurationPicker(5, 24 * 60)
        self._default_focus_mode.currentIndexChanged.connect(
            self._emit_focus_timer_preferences
        )
        self._default_focus_target_minutes.valueChanged.connect(
            self._emit_focus_timer_preferences
        )
        self._add_row(
            self._timer_form, "settings.default_focus_mode", self._default_focus_mode
        )
        self._add_row(
            self._timer_form,
            "settings.default_focus_target",
            self._default_focus_target_minutes,
        )

    def _build_companion_preferences(self) -> None:
        self._always_on_top = self._checkbox("settings.always_on_top")
        self._start_with_windows = self._checkbox("settings.startup")
        self._notifications_enabled = self._checkbox("settings.notifications")
        self._always_on_top.toggled.connect(self._emit_application_preferences)
        self._start_with_windows.toggled.connect(self._emit_application_preferences)
        self._notifications_enabled.toggled.connect(self._emit_application_preferences)
        self._always_on_top_row = self._add_checkbox_row(
            self._companion_form, "settings.always_on_top", self._always_on_top
        )
        self._start_with_windows_row = self._add_checkbox_row(
            self._companion_form, "settings.startup", self._start_with_windows
        )
        self._notifications_enabled_row = self._add_checkbox_row(
            self._companion_form, "settings.notifications", self._notifications_enabled
        )

    def _build_data_page(self) -> None:
        self._data_saved_label = QLabel()
        self._data_saved_label.setWordWrap(True)
        self._data_saved_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._data_location_label = QLabel()
        self._data_location_label.setWordWrap(True)
        self._data_location_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._data_location_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._open_data_folder_button = self._button(
            "settings.open_data_folder", self._open_data_folder
        )
        data_location_layout = QVBoxLayout()
        data_location_layout.setContentsMargins(0, 0, 0, 0)
        data_location_layout.setSpacing(8)
        data_location_layout.addWidget(self._data_location_label, stretch=1)
        data_location_layout.addWidget(self._open_data_folder_button)
        data_location_controls = QWidget()
        data_location_controls.setLayout(data_location_layout)
        self._add_row(self._data_form, "settings.data", self._data_saved_label)
        self._add_row(
            self._data_form, "settings.data_location", data_location_controls
        )

    def _build_about_page(self) -> None:
        self._about_description = QLabel()
        self._about_description.setWordWrap(True)
        self._about_description.setObjectName("pageSubtitle")
        self._translated_widgets.append(
            (self._about_description, "settings.about_description")
        )
        self._about_languages = QLabel(
            ", ".join(language.native_name for language in SUPPORTED_LANGUAGES)
        )
        self._about_languages.setWordWrap(True)
        self._add_row(self._about_form, "settings.about_product", self._about_description)
        self._add_row(self._about_form, "settings.about_version", QLabel(__version__))
        self._add_row(
            self._about_form, "settings.about_languages", self._about_languages
        )

    def _build_dialog_shell(self) -> None:
        self._close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._close_buttons.rejected.connect(self.close)
        self._help_label = QLabel()
        self._help_label.setWordWrap(True)

        sidebar = QFrame()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setMinimumWidth(176)
        sidebar.setMaximumWidth(208)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 18)
        sidebar_layout.setSpacing(6)
        for button in self._nav_buttons:
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 18)
        content_layout.setSpacing(10)
        page_region = QWidget()
        page_region_layout = QVBoxLayout(page_region)
        page_region_layout.setContentsMargins(0, 0, 0, 0)
        page_region_layout.setSpacing(10)
        page_region_layout.addWidget(self._page_title)
        page_region_layout.addWidget(self._tabs, stretch=1)
        self._tabs.set_transition_target(page_region)
        content_layout.addWidget(page_region, stretch=1)
        content_layout.addWidget(self._status_label)
        content_layout.addWidget(self._help_label)
        content_layout.addWidget(self._close_buttons)

        layout = QHBoxLayout(cast(QWidget, self))
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(content, stretch=1)
