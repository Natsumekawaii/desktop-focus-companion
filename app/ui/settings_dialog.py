"""Five-section settings for Desktop Focus Companion desktop companion and focus tracking."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.core.icon_system import IconName, IconSystem
from app.core.theme import COLOR_THEMES, THEME_TOKENS, get_theme_manager
from app.data.settings_repository import MAX_PET_SIZE_PERCENT, MIN_PET_SIZE_PERCENT
from app.focus_mode import FocusMode
from app.i18n import SUPPORTED_LANGUAGES, get_localization, tr
from app.ui.components import DurationPicker, RoundedCheckBox
from app.ui.page_transition import AnimatedPageStack
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity

_SETTING_DESCRIPTIONS = {
    "settings.current_pet",
    "settings.pet_image",
    "settings.pet_size",
    "settings.current_app_icon",
    "settings.application_icon",
    "settings.language",
    "settings.color_theme",
    "settings.daily_goal",
    "settings.weekly_goal",
    "settings.minimum_streak",
    "settings.default_focus_mode",
    "settings.default_focus_target",
    "settings.data_location",
    "settings.always_on_top",
    "settings.startup",
    "settings.notifications",
}


class _SettingsPageStack(AnimatedPageStack):
    """Stacked settings pages with the legacy tab inspection API.

    Older integrations inspect ``_tabs`` to retrieve translated labels and
    icons.  Keeping those tiny accessors lets the visible UI move to a sidebar
    without changing any controller-facing behavior.
    """

    TabPosition = QTabWidget.TabPosition

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._icons: list[QIcon] = []

    def addPage(self, widget: QWidget, label: str = "") -> int:
        index = self.addWidget(widget)
        self._labels.insert(index, label)
        self._icons.insert(index, QIcon())
        return index

    def setTabText(self, index: int, text: str) -> None:
        self._labels[index] = text

    def tabText(self, index: int) -> str:
        return self._labels[index]

    def setTabIcon(self, index: int, icon: QIcon) -> None:
        self._icons[index] = icon

    def tabIcon(self, index: int) -> QIcon:
        return self._icons[index]

    def tabPosition(self) -> QTabWidget.TabPosition:
        return QTabWidget.TabPosition.North


class SettingsDialog(QDialog):
    """Collect preferences without performing persistence in the UI layer."""

    import_requested = Signal(Path)
    use_default_requested = Signal()
    app_icon_import_requested = Signal(Path)
    use_default_app_icon_requested = Signal()
    size_changed = Signal(int)
    language_changed = Signal(str)
    color_theme_changed = Signal(str)
    focus_goal_preferences_changed = Signal(int, int, int)
    focus_timer_preferences_changed = Signal(str, int)
    application_preferences_changed = Signal(bool, bool, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(620)
        self.setMinimumHeight(440)
        self.resize(760, 680)
        self._startup_supported = True
        self._current_pet_name = ""
        self._current_pet_default = True
        self._current_pet_note: str | None = None
        self._current_app_icon_name = ""
        self._current_app_icon_default = True
        self._current_app_icon_note: str | None = None
        self._current_app_icon_path: Path | None = None
        self._data_location_path: Path | None = None
        self._translated_widgets: list[tuple[QWidget, str]] = []

        image_controls, size_controls = self._build_companion_controls()
        self._build_page_stack(image_controls, size_controls)
        self._build_appearance_page()
        self._build_timer_page()
        self._build_companion_preferences()
        self._build_data_page()
        self._build_about_page()
        self._build_dialog_shell()
        get_localization().language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

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

        self._nav_group = QButtonGroup(self)
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
        self._theme_button_group = QButtonGroup(self)
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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(content, stretch=1)


    def retranslate_ui(self, _language: str | None = None) -> None:
        """Refresh every static and derived string while the dialog is open."""
        self.setWindowTitle(tr("settings.title"))
        for index, key in enumerate(
            (
                "settings.tab.appearance",
                "settings.tab.companion",
                "settings.tab.timer",
                "settings.tab.data",
                "settings.tab.about",
            )
        ):
            text = tr(key)
            self._tabs.setTabText(index, text)
            self._nav_buttons[index].setText(text)
            self._nav_buttons[index].setToolTip(text)
            self._nav_buttons[index].setAccessibleName(text)
        self._page_title.setText(self._tabs.tabText(self._tabs.currentIndex()))
        for widget, key in self._translated_widgets:
            if isinstance(widget, (QLabel, QPushButton)):
                widget.setText(tr(key))
        for checkbox in self.findChildren(RoundedCheckBox):
            key = checkbox.property("translationKey")
            if isinstance(key, str):
                checkbox.setText(tr(key))
                checkbox.setAccessibleName(tr(key))
                checkbox.setToolTip(tr(f"{key}.description"))
        self._help_label.setText(tr("settings.tip"))
        close = self._close_buttons.button(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setText(tr("common.close"))
        self._default_focus_mode.setItemText(0, tr("quick.mode.stopwatch"))
        self._default_focus_mode.setItemText(1, tr("quick.mode.countdown"))
        self._data_saved_label.setText(tr("settings.data_saved_automatically"))
        blocked = self._color_theme_combo.blockSignals(True)
        for index, theme_name in enumerate(COLOR_THEMES):
            theme_label = tr(f"settings.theme.{theme_name}")
            self._color_theme_combo.setItemText(index, theme_label)
            self._theme_buttons[index].setToolTip(theme_label)
            self._theme_buttons[index].setAccessibleName(theme_label)
        self._color_theme_combo.blockSignals(blocked)
        self._sync_theme_picker()
        self._refresh_current_pet_text()
        self._refresh_current_app_icon_text()

    def set_language(self, language: str) -> None:
        index = self._language_combo.findData(language)
        if index < 0:
            return
        blocked = self._language_combo.blockSignals(True)
        self._language_combo.setCurrentIndex(index)
        self._language_combo.blockSignals(blocked)

    def set_size_percent(self, value: int) -> None:
        blocked = self._size_slider.blockSignals(True)
        self._size_slider.setValue(value)
        self._size_slider.blockSignals(blocked)
        self._size_value_label.setText(f"{value}%")

    def set_color_theme(self, theme_name: str) -> None:
        index = self._color_theme_combo.findData(theme_name)
        if index < 0:
            return
        blocked = self._color_theme_combo.blockSignals(True)
        self._color_theme_combo.setCurrentIndex(index)
        self._color_theme_combo.blockSignals(blocked)
        self._sync_theme_picker()

    def set_current_pet(self, display_name: str, using_default: bool, note: str | None = None) -> None:
        self._current_pet_name = display_name
        self._current_pet_default = using_default
        self._current_pet_note = note
        self._refresh_current_pet_text()

    def set_current_application_icon(
        self,
        icon_path: Path,
        display_name: str,
        using_default: bool,
        note: str | None = None,
    ) -> None:
        self._current_app_icon_path = icon_path
        self._current_app_icon_name = display_name
        self._current_app_icon_default = using_default
        self._current_app_icon_note = note
        icon = QIcon(str(icon_path))
        if icon.isNull():
            self._app_icon_preview.clear()
        else:
            self._app_icon_preview.setPixmap(icon.pixmap(48, 48))
        self._refresh_current_app_icon_text()

    def set_focus_goal_preferences(
        self,
        daily_goal_minutes: int,
        weekly_goal_minutes: int,
        streak_minutes: int,
    ) -> None:
        daily_blocked = self._daily_goal_minutes.blockSignals(True)
        weekly_blocked = self._weekly_goal_minutes.blockSignals(True)
        streak_blocked = self._streak_minutes.blockSignals(True)
        self._daily_goal_minutes.setValue(daily_goal_minutes)
        self._weekly_goal_minutes.setValue(weekly_goal_minutes)
        self._streak_minutes.setValue(streak_minutes)
        self._daily_goal_minutes.blockSignals(daily_blocked)
        self._weekly_goal_minutes.blockSignals(weekly_blocked)
        self._streak_minutes.blockSignals(streak_blocked)

    def set_focus_timer_preferences(
        self, mode: FocusMode | str, target_minutes: int
    ) -> None:
        mode_value = mode.value if isinstance(mode, FocusMode) else mode
        mode_index = self._default_focus_mode.findData(mode_value)
        mode_blocked = self._default_focus_mode.blockSignals(True)
        target_blocked = self._default_focus_target_minutes.blockSignals(True)
        if mode_index >= 0:
            self._default_focus_mode.setCurrentIndex(mode_index)
        self._default_focus_target_minutes.setValue(target_minutes)
        self._default_focus_mode.blockSignals(mode_blocked)
        self._default_focus_target_minutes.blockSignals(target_blocked)

    def set_application_preferences(
        self,
        always_on_top: bool,
        start_with_windows: bool,
        notifications_enabled: bool,
        startup_supported: bool | None = None,
    ) -> None:
        top_blocked = self._always_on_top.blockSignals(True)
        startup_blocked = self._start_with_windows.blockSignals(True)
        notification_blocked = self._notifications_enabled.blockSignals(True)
        self._always_on_top.setChecked(always_on_top)
        self._start_with_windows.setChecked(start_with_windows)
        if startup_supported is not None:
            self._startup_supported = startup_supported
        self._start_with_windows_row.setEnabled(self._startup_supported)
        self._notifications_enabled.setChecked(notifications_enabled)
        self._always_on_top.blockSignals(top_blocked)
        self._start_with_windows.blockSignals(startup_blocked)
        self._notifications_enabled.blockSignals(notification_blocked)

    def set_data_location(self, path: Path) -> None:
        self._data_location_path = path
        self._data_location_label.setText(str(path))

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, tr("app.name"), message)

    def open_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _form_tab(self) -> tuple[QWidget, QFormLayout]:
        widget = QWidget()
        widget.setObjectName("settingsPage")
        page_layout = QVBoxLayout(widget)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QFrame()
        content.setObjectName("settingsSection")
        form = QFormLayout(content)
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(0)
        form.setVerticalSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # Settings use one predictable pattern at every window width:
        # title and supporting text first, then the full-width control.  This
        # prevents the label column from collapsing at the minimum width and
        # keeps English descriptions readable without horizontal scrolling.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return widget, form

    def _refresh_icons(self) -> None:
        icons = (
            IconName.APPEARANCE,
            IconName.COMPANION,
            IconName.TIMER,
            IconName.DATA,
            IconName.ABOUT,
        )
        for index, name in enumerate(icons):
            icon = IconSystem.icon(name)
            self._tabs.setTabIcon(index, icon)
            self._nav_buttons[index].setIcon(icon)

    def _select_page(self, index: int) -> None:
        if not 0 <= index < self._tabs.count():
            return
        self._tabs.setCurrentIndex(index)

    def _on_page_changed(self, index: int) -> None:
        if not 0 <= index < self._tabs.count():
            return
        self._nav_buttons[index].setChecked(True)
        self._page_title.setText(self._tabs.tabText(index))

    def _add_row(self, form: QFormLayout, key: str, field: QWidget) -> None:
        label_widget = QWidget()
        label_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        label_layout = QVBoxLayout(label_widget)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(2)
        label = QLabel()
        label.setObjectName("settingsRowTitle")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label_layout.addWidget(label)
        self._translated_widgets.append((label, key))
        if key in _SETTING_DESCRIPTIONS:
            description = QLabel()
            description.setObjectName("supportingText")
            description.setWordWrap(True)
            description.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            label_layout.addWidget(description)
            self._translated_widgets.append((description, f"{key}.description"))
        form.addRow(label_widget, field)

    def _button(self, key: str, callback: object) -> QPushButton:
        button = QPushButton()
        self._translated_widgets.append((button, key))
        button.clicked.connect(cast(Callable[..., object], callback))
        return button

    def _add_checkbox_row(
        self,
        form: QFormLayout,
        key: str,
        checkbox: RoundedCheckBox,
    ) -> QWidget:
        row = QFrame()
        row.setObjectName("booleanSettingRow")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(checkbox)

        description = QLabel()
        description.setObjectName("supportingText")
        description.setWordWrap(True)
        description.setContentsMargins(30, 0, 0, 0)
        description.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(description)
        self._translated_widgets.append((description, f"{key}.description"))
        form.addRow(row)
        return row

    def _checkbox(self, key: str) -> RoundedCheckBox:
        checkbox = RoundedCheckBox()
        checkbox.setProperty("translationKey", key)
        checkbox.setAccessibleName(tr(key))
        checkbox.setToolTip(tr(f"{key}.description"))
        return checkbox

    def _choose_image(self) -> None:
        selected_file, _ = QFileDialog.getOpenFileName(
            self, tr("file.import_pet_title"), "", tr("file.pet_images_filter")
        )
        if selected_file:
            self.import_requested.emit(Path(selected_file))

    def _choose_app_icon(self) -> None:
        selected_file, _ = QFileDialog.getOpenFileName(
            self, tr("file.import_app_icon_title"), "", tr("file.app_icon_images_filter")
        )
        if selected_file:
            self.app_icon_import_requested.emit(Path(selected_file))

    def _on_size_value_changed(self, value: int) -> None:
        self._size_value_label.setText(f"{value}%")
        self.size_changed.emit(value)

    def _on_language_selected(self) -> None:
        language = self._language_combo.currentData()
        if isinstance(language, str):
            self.language_changed.emit(language)

    def _emit_focus_goal_preferences(self) -> None:
        self.focus_goal_preferences_changed.emit(
            self._daily_goal_minutes.value(),
            self._weekly_goal_minutes.value(),
            self._streak_minutes.value(),
        )

    def _emit_focus_timer_preferences(self) -> None:
        mode = self._default_focus_mode.currentData()
        if isinstance(mode, str):
            self.focus_timer_preferences_changed.emit(
                mode, self._default_focus_target_minutes.value()
            )

    def _emit_application_preferences(self) -> None:
        self.application_preferences_changed.emit(
            self._always_on_top.isChecked(),
            self._start_with_windows.isChecked(),
            self._notifications_enabled.isChecked(),
        )

    def _open_data_folder(self) -> None:
        if self._data_location_path is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._data_location_path))):
            self.show_error(tr("error.open_data_folder"))

    def _on_color_theme_selected(self) -> None:
        theme_name = self._color_theme_combo.currentData()
        if isinstance(theme_name, str):
            self._sync_theme_picker()
            self.color_theme_changed.emit(theme_name)

    def _sync_theme_picker(self) -> None:
        selected = self._color_theme_combo.currentIndex()
        for index, button in enumerate(self._theme_buttons):
            blocked = button.blockSignals(True)
            button.setChecked(index == selected)
            button.blockSignals(blocked)

    def _refresh_current_pet_text(self) -> None:
        if self._current_pet_name:
            source = tr("common.default") if self._current_pet_default else tr("common.custom")
            self._current_pet_label.setText(
                tr("settings.pet_source", source=source, name=self._current_pet_name)
            )
        self._status_label.setText(self._current_pet_note or "")

    def _refresh_current_app_icon_text(self) -> None:
        if not self._current_app_icon_name:
            return
        source = (
            tr("common.default") if self._current_app_icon_default else tr("common.custom")
        )
        description = tr(
            "settings.app_icon_source",
            source=source,
            name=self._current_app_icon_name,
        )
        if self._current_app_icon_note:
            description = f"{description}\n{self._current_app_icon_note}"
        self._current_app_icon_label.setText(description)
        self._app_icon_preview.setToolTip(self._current_app_icon_note or self._current_app_icon_name)


def _theme_swatch_icon(theme_name: str) -> QIcon:
    tokens = THEME_TOKENS[theme_name]
    pixmap = QPixmap(34, 34)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(tokens.border), 1))
    painter.setBrush(QColor(tokens.canvas))
    painter.drawRoundedRect(1, 1, 32, 32, 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(tokens.surface))
    painter.drawRoundedRect(6, 7, 22, 20, 5, 5)
    painter.setBrush(QColor(tokens.primary))
    painter.drawEllipse(17, 13, 9, 9)
    painter.end()
    return QIcon(pixmap)
