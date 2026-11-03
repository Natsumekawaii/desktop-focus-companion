"""Five-section settings for Desktop Focus Companion desktop companion and focus tracking."""

from __future__ import annotations

from app.core.theme import get_theme_manager
from app.data.settings_repository import MAX_PET_SIZE_PERCENT, MIN_PET_SIZE_PERCENT
from app.i18n import SUPPORTED_LANGUAGES
from app.ui.components import DurationPicker
from app.ui.rounded_selector import RoundedComboBox, SelectorDensity

# Compatibility exports for existing integrations and focused UI tests.
__all__ = ["MAX_PET_SIZE_PERCENT", "MIN_PET_SIZE_PERCENT", "SUPPORTED_LANGUAGES", "DurationPicker", "RoundedComboBox", "SelectorDensity", "SettingsDialog", "get_theme_manager"]

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.icon_system import IconName, IconSystem
from app.core.theme import COLOR_THEMES, THEME_TOKENS
from app.focus_mode import FocusMode
from app.i18n import get_localization, tr
from app.ui.components import RoundedCheckBox
from app.ui.page_transition import AnimatedPageStack
from app.ui.settings_dialog_builders import _SettingsDialogBuilders

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


class SettingsDialog(_SettingsDialogBuilders, QDialog):
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
