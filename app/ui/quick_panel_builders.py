"""Private FocusPanel control construction; behavior stays in the public window."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.ui.components import CircularTimerWidget, DurationPicker
from app.ui.focus_item_selector import (
    FocusItemSelector,
)
from app.ui.focus_panel_motion import (
    SmoothProgressBar,
)
from app.ui.pre_focus_countdown import PreFocusCountdownWidget
from app.ui.rounded_selector import SelectorDensity


class _FocusPanelBuilders:
    # Construction calls hooks supplied by the concrete Qt window. This bridge
    # is type-checking-only; it does not change runtime attribute lookup.
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...

    def _build_header(self) -> None:
        self._title = QLabel()
        self._title.setObjectName("title")
        self._close_button = QPushButton("×")
        self._close_button.setObjectName("iconButton")
        self._close_button.setFixedSize(30, 30)
        close_font = QFont(self._close_button.font())
        close_font.setPointSize(16)
        close_font.setWeight(QFont.Weight.DemiBold)
        self._close_button.setFont(close_font)
        self._close_button.clicked.connect(self._hide_panel)
        self._header_drag_surface = QFrame()
        self._header_drag_surface.setObjectName("focusPanelHeader")
        self._header_drag_surface.setCursor(Qt.CursorShape.OpenHandCursor)
        header = QHBoxLayout(self._header_drag_surface)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(self._close_button)
        self._header_drag_surface.installEventFilter(cast(QWidget, self))
        self._title.installEventFilter(cast(QWidget, self))

    def _build_idle_page(self) -> None:
        # Idle page: a compact daily summary followed by the launch controls.
        self._today_caption = QLabel()
        self._today_caption.setObjectName("cardCaption")
        self._today_value = QLabel(tr("duration.zero"))
        self._today_value.setObjectName("todayValue")
        self._today_value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._goal_progress = SmoothProgressBar()
        self._goal_progress.setRange(0, 1000)
        self._goal_progress.setTextVisible(False)
        self._goal_progress.setFixedHeight(10)
        self._daily_goal_label = QLabel()
        self._daily_goal_label.setObjectName("secondary")
        self._weekly_goal_label = QLabel()
        self._weekly_goal_label.setObjectName("secondary")
        self._weekly_goal_progress = SmoothProgressBar()
        self._weekly_goal_progress.setRange(0, 1000)
        self._weekly_goal_progress.setTextVisible(False)
        self._weekly_goal_progress.setFixedHeight(10)
        self._streak_label = QLabel()
        self._streak_label.setObjectName("secondary")

        summary = QFrame()
        summary.setObjectName("focusSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(6)
        summary_header = QHBoxLayout()
        today_column = QVBoxLayout()
        today_column.setSpacing(1)
        today_column.addWidget(self._today_caption)
        today_column.addWidget(self._today_value)
        summary_header.addLayout(today_column, stretch=1)
        summary_header.addWidget(
            self._streak_label, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        summary_layout.addLayout(summary_header)
        summary_layout.addWidget(self._daily_goal_label)
        summary_layout.addWidget(self._goal_progress)
        summary_layout.addWidget(self._weekly_goal_label)
        summary_layout.addWidget(self._weekly_goal_progress)

        self._focus_item_combo = FocusItemSelector()
        self._focus_item_combo.setObjectName("focusItemSelector")
        self._focus_item_combo.setFixedHeight(48)
        self._focus_item_combo.setMaxVisibleItems(12)
        self._focus_item_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._focus_item_combo.setMinimumContentsLength(12)
        self._focus_item_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self._focus_item_combo.currentIndexChanged.connect(
            self._on_focus_item_index_changed
        )
        self._focus_item_combo.activated.connect(self._on_focus_item_activated)
        self._selection_widget = QWidget()
        selection_layout = QVBoxLayout(self._selection_widget)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(7)
        self._focus_item_caption = QLabel()
        self._focus_item_caption.setBuddy(self._focus_item_combo)
        self._subject_combo = self._focus_item_combo
        self._subject_caption = self._focus_item_caption
        selection_layout.addWidget(self._focus_item_caption)
        selection_layout.addWidget(self._focus_item_combo)

        self._mode_caption = QLabel()
        self._stopwatch_radio = QRadioButton()
        self._countdown_radio = QRadioButton()
        self._stopwatch_radio.setObjectName("segmentButton")
        self._countdown_radio.setObjectName("segmentButton")
        self._stopwatch_radio.setChecked(True)
        self._mode_group = QButtonGroup(cast(QWidget, self))
        self._mode_group.addButton(self._stopwatch_radio)
        self._mode_group.addButton(self._countdown_radio)
        segmented_control = QFrame()
        segmented_control.setObjectName("segmentedControl")
        mode_row = QHBoxLayout(segmented_control)
        mode_row.setContentsMargins(3, 3, 3, 3)
        mode_row.setSpacing(3)
        self._stopwatch_radio.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self._countdown_radio.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        mode_row.addWidget(self._stopwatch_radio, 1)
        mode_row.addWidget(self._countdown_radio, 1)
        selection_layout.addWidget(self._mode_caption)
        selection_layout.addWidget(segmented_control)

        self._target_controls = QWidget()
        target_layout = QVBoxLayout(self._target_controls)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(7)
        self._target_caption = QLabel()
        self._target_duration_picker = DurationPicker(
            5,
            24 * 60,
            density=SelectorDensity.LARGE,
        )
        target_layout.addWidget(self._target_caption)
        target_layout.addWidget(self._target_duration_picker)
        selection_layout.addWidget(self._target_controls)
        self._countdown_radio.toggled.connect(self._update_target_controls_visibility)
        self._update_target_controls_visibility()

        self._note_input = QLineEdit()
        self._note_input.setMaxLength(2000)
        self._note_toggle = QPushButton()
        self._note_toggle.setObjectName("disclosureButton")
        self._note_toggle.setCheckable(True)
        self._note_toggle.toggled.connect(self._toggle_note)
        self._note_caption = self._note_toggle
        selection_layout.addWidget(self._note_toggle)
        selection_layout.addWidget(self._note_input)
        self._note_input.setVisible(False)

        self._start_button = QPushButton()
        self._start_button.setObjectName("primary")
        self._start_button.clicked.connect(self._request_start)

        idle_content = QWidget()
        idle_layout = QVBoxLayout(idle_content)
        idle_layout.setContentsMargins(0, 0, 4, 0)
        idle_layout.setSpacing(10)
        idle_layout.addWidget(summary)
        idle_layout.addWidget(self._selection_widget)
        idle_layout.addStretch()
        idle_layout.addWidget(self._start_button)
        idle_scroll = QScrollArea()
        idle_scroll.setObjectName("focusPanelScroll")
        idle_scroll.setFrameShape(QFrame.Shape.NoFrame)
        idle_scroll.setWidgetResizable(True)
        idle_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        idle_scroll.setWidget(idle_content)
        self._idle_page = idle_scroll

    def _build_active_page(self) -> None:
        # Active page: one stable timer surface with only legal session actions.
        self._state_label = QLabel()
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setObjectName("statusPill")
        self._active_focus_item_label = QLabel()
        self._active_focus_item_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._active_focus_item_label.setObjectName("sectionTitle")
        self._active_focus_item_label.setWordWrap(True)
        self._active_focus_item_label.setMaximumHeight(52)
        self._mode_status_label = QLabel()
        self._mode_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_status_label.setObjectName("secondary")
        self._target_summary_label = QLabel()
        self._target_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._remaining_value = QLabel("00:00:00")
        self._remaining_value.setObjectName("timerValue")
        self._remaining_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer_value = QLabel("00:00:00")
        self._timer_value.setObjectName("stopwatchTimerValue")
        self._timer_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._minimum_recording_hint = QLabel()
        self._minimum_recording_hint.setObjectName("secondary")
        self._minimum_recording_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._minimum_recording_hint.setWordWrap(True)
        self._timer_ring = CircularTimerWidget()

        countdown_visual = QWidget()
        countdown_visual_layout = QHBoxLayout(countdown_visual)
        countdown_visual_layout.setContentsMargins(0, 0, 0, 0)
        countdown_visual_layout.addStretch()
        countdown_visual_layout.addWidget(self._timer_ring)
        countdown_visual_layout.addStretch()

        stopwatch_visual = QWidget()
        stopwatch_visual_layout = QVBoxLayout(stopwatch_visual)
        stopwatch_visual_layout.setContentsMargins(0, 0, 0, 0)
        stopwatch_visual_layout.addStretch()
        stopwatch_visual_layout.addWidget(
            self._timer_value, alignment=Qt.AlignmentFlag.AlignCenter
        )
        stopwatch_visual_layout.addStretch()

        self._timer_visual_stack = QStackedWidget()
        self._timer_visual_stack.setObjectName("timerVisualStack")
        self._timer_visual_stack.setMinimumHeight(220)
        self._timer_visual_stack.addWidget(countdown_visual)
        self._timer_visual_stack.addWidget(stopwatch_visual)
        self._countdown_visual = countdown_visual
        self._stopwatch_visual = stopwatch_visual

        self._pause_button = QPushButton()
        self._pause_button.setObjectName("primary")
        self._pause_button.clicked.connect(self.pause_requested)
        self._resume_button = QPushButton()
        self._resume_button.setObjectName("primary")
        self._resume_button.clicked.connect(self.resume_requested)
        self._finish_button = QPushButton()
        self._finish_button.setObjectName("danger")
        self._finish_button.clicked.connect(self.finish_requested)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self._pause_button)
        action_row.addWidget(self._resume_button)
        action_row.addWidget(self._finish_button)

        active_content = QWidget()
        active_layout = QVBoxLayout(active_content)
        active_layout.setContentsMargins(4, 6, 4, 4)
        active_layout.setSpacing(8)
        active_layout.addWidget(
            self._state_label, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        active_layout.addWidget(self._active_focus_item_label)
        active_layout.addWidget(self._mode_status_label)
        active_layout.addWidget(self._target_summary_label)
        active_layout.addStretch()
        active_layout.addWidget(self._timer_visual_stack)
        active_layout.addStretch()
        active_layout.addWidget(self._minimum_recording_hint)
        active_layout.addLayout(action_row)
        active_scroll = QScrollArea()
        active_scroll.setObjectName("focusPanelScroll")
        active_scroll.setFrameShape(QFrame.Shape.NoFrame)
        active_scroll.setWidgetResizable(True)
        active_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        active_scroll.setWidget(active_content)
        self._active_page = active_scroll

    def _build_prestart_page(self, countdown_phase_duration_ms: int) -> None:
        self._prestart_animation = PreFocusCountdownWidget(
            phase_duration_ms=countdown_phase_duration_ms
        )
        self._prestart_animation.completed.connect(self._complete_prestart)
        prestart_scroll = QScrollArea()
        prestart_scroll.setObjectName("focusPanelScroll")
        prestart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        prestart_scroll.setWidgetResizable(True)
        prestart_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        prestart_scroll.setWidget(self._prestart_animation)
        self._prestart_page = prestart_scroll

    def _build_panel_surface(self) -> None:
        self._panel_stack = QStackedWidget()
        self._panel_stack.setObjectName("focusPanelStack")
        self._panel_stack.addWidget(self._idle_page)
        self._panel_stack.addWidget(self._active_page)
        self._panel_stack.addWidget(self._prestart_page)

        self._surface = QFrame()
        self._surface.setObjectName("focusPanelSurface")
        surface_layout = QVBoxLayout(self._surface)
        surface_layout.setContentsMargins(18, 14, 18, 18)
        surface_layout.setSpacing(10)
        surface_layout.addWidget(self._header_drag_surface)
        surface_layout.addWidget(self._panel_stack, stretch=1)

        layout = QVBoxLayout(cast(QWidget, self))
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self._surface)
