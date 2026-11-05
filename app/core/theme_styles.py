"""Pure palette and QSS generation; ordering and text are compatibility contracts."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from app.core.theme_tokens import DESIGN, ThemeTokens


def _palette(tokens: ThemeTokens) -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: tokens.canvas,
        QPalette.ColorRole.WindowText: tokens.text,
        QPalette.ColorRole.Base: tokens.input,
        QPalette.ColorRole.AlternateBase: tokens.surface_alt,
        QPalette.ColorRole.ToolTipBase: tokens.surface,
        QPalette.ColorRole.ToolTipText: tokens.text,
        QPalette.ColorRole.Text: tokens.text,
        QPalette.ColorRole.Button: tokens.surface,
        QPalette.ColorRole.ButtonText: tokens.text,
        QPalette.ColorRole.Highlight: tokens.primary,
        QPalette.ColorRole.HighlightedText: tokens.primary_text,
        QPalette.ColorRole.PlaceholderText: tokens.muted,
        QPalette.ColorRole.Link: tokens.primary,
        QPalette.ColorRole.LinkVisited: tokens.primary_pressed,
        QPalette.ColorRole.Light: tokens.surface_elevated,
        QPalette.ColorRole.Mid: tokens.border,
        QPalette.ColorRole.Dark: tokens.border_strong,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.disabled))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(tokens.disabled),
    )
    return palette


def _style_sheet(tokens: ThemeTokens) -> str:
    return "".join(
        (
            _base_style_sheet(tokens),
            _navigation_style_sheet(tokens),
            _surface_style_sheet(tokens),
            _typography_style_sheet(tokens),
            _control_style_sheet(tokens),
            _input_style_sheet(tokens),
            _floating_style_sheet(tokens),
        )
    )


def _base_style_sheet(tokens: ThemeTokens) -> str:
    return f"""
        * {{
            font-size: {DESIGN.font_body}px;
        }}
        QMainWindow, QDialog, QMessageBox, QScrollArea {{
            background: {tokens.canvas}; color: {tokens.text};
        }}
        QWidget {{
            color: {tokens.text};
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QLabel {{ background: transparent; }}
        QFrame#appShell, QFrame#settingsPage, QWidget#settingsPage,
        QStackedWidget#focusPanelStack, QStackedWidget#timerVisualStack {{
            background: transparent; border: 0;
        }}

"""


def _navigation_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Navigation shells */
        QFrame#sidebar, QFrame#settingsSidebar {{
            background: {tokens.surface};
            border: 0; border-right: 1px solid {tokens.separator};
        }}
        QLabel#navigationGroup {{
            color: {tokens.text_subtle}; font-size: {DESIGN.font_caption}px;
            font-weight: 700; padding: 12px 12px 4px 12px;
        }}
        QToolButton#dashboardSidebarToggle {{
            background: transparent; color: {tokens.muted};
            border: 1px solid transparent; border-radius: 6px;
            min-width: 30px; min-height: 30px; padding: 0;
        }}
        QToolButton#dashboardSidebarToggle:hover {{ background: {tokens.surface_hover}; }}
        QToolButton#dashboardSidebarToggle:pressed {{ background: {tokens.primary_soft}; }}
        QToolButton#dashboardSidebarToggle:focus {{ border-color: {tokens.focus_ring}; }}
        QToolButton#navigationButton, QPushButton#navigationButton,
        QPushButton#sidebarNavButton {{
            background: transparent; color: {tokens.muted};
            border: 1px solid transparent; border-radius: {DESIGN.radius_sm}px;
            min-height: 24px; padding: 8px 12px; text-align: left;
            font-weight: 600;
        }}
        QToolButton#navigationButton:hover, QPushButton#navigationButton:hover,
        QPushButton#sidebarNavButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QToolButton#navigationButton:pressed, QPushButton#navigationButton:pressed,
        QPushButton#sidebarNavButton:pressed {{
            background: {tokens.primary_soft}; color: {tokens.primary};
        }}
        QToolButton#navigationButton:checked, QPushButton#navigationButton:checked,
        QPushButton#sidebarNavButton:checked {{
            background: {tokens.primary_soft}; color: {tokens.primary};
            border-color: {tokens.separator};
        }}
        QToolButton#navigationButton:focus, QPushButton#navigationButton:focus,
        QPushButton#sidebarNavButton:focus {{
            border-color: {tokens.focus_ring};
        }}
        QFrame#sidebar QToolButton#navigationButton {{ padding: 8px; }}

"""


def _surface_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Surface hierarchy */
        QDialog#quickPanel {{
            background: transparent; border: none;
        }}
        QFrame#focusPanelSurface {{
            background: {tokens.surface_elevated}; border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#card {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#heroCard {{
            background: {tokens.primary_soft}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#softCard {{
            background: {tokens.surface_alt}; border: 1px solid transparent;
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#sectionSurface {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#settingsSection {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_lg}px;
        }}
        QFrame#focusSummary {{
            background: {tokens.primary_soft}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#metricStrip {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#metricItem {{ background: transparent; border: 0; }}
        QFrame#emptyState {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#listRow {{
            background: transparent; border: 1px solid transparent;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QFrame#listRow:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.separator};
        }}
        QFrame#focusItemCard {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#focusItemCard:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QListWidget#focusItemManagementList {{
            padding: 4px 0; border-radius: {DESIGN.radius_md}px;
            outline: 0; selection-background-color: transparent;
        }}
        QListWidget#focusItemManagementList::item {{
            background: transparent; border: 0; padding: 0; outline: 0;
        }}
        QListWidget#focusItemManagementList::item:hover,
        QListWidget#focusItemManagementList::item:selected {{
            background: transparent; color: {tokens.text};
        }}
        QFrame#focusItemManagementCard {{
            background: {tokens.surface}; border: 1px solid {tokens.separator};
            border-radius: {DESIGN.radius_md + 2}px;
        }}
        QFrame#focusItemManagementCard:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QFrame#focusItemManagementCard[selected="true"] {{
            background: {tokens.primary_soft}; border-color: {tokens.focus_ring};
        }}
        QWidget#distributionRow {{
            background: transparent; border-radius: {DESIGN.radius_sm}px;
        }}
        QWidget#distributionRow:hover {{ background: {tokens.surface_hover}; }}

"""


def _typography_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Type hierarchy */
        QLabel#pageTitle {{
            color: {tokens.text}; font-size: {DESIGN.font_title}px; font-weight: 700;
        }}
        QLabel#pageSubtitle {{
            color: {tokens.muted}; font-size: {DESIGN.font_body_lg}px;
        }}
        QLabel#sectionTitle, QLabel#title {{
            color: {tokens.text}; font-size: {DESIGN.font_section}px; font-weight: 700;
        }}
        QLabel#cardCaption {{
            color: {tokens.muted}; font-size: 12px; font-weight: 600;
        }}
        QLabel#metricValue, QLabel#todayValue, QLabel#timerValue {{
            color: {tokens.primary}; font-size: 25px; font-weight: 700;
        }}
        QLabel#stopwatchTimerValue {{
            color: {tokens.primary}; font-size: 42px; font-weight: 700;
        }}
        QLabel#heroValue {{
            color: {tokens.primary}; font-size: {DESIGN.font_display}px; font-weight: 700;
        }}
        QLabel#emptyStateIcon {{
            color: {tokens.primary}; font-size: 26px; font-weight: 600;
        }}
        QLabel#emptyStateTitle {{
            color: {tokens.text}; font-size: {DESIGN.font_section}px; font-weight: 700;
        }}
        QLabel#emptyStateMessage, QLabel#supportingText {{
            color: {tokens.muted}; font-size: {DESIGN.font_body}px;
        }}
        QLabel#statusPill {{
            background: {tokens.primary}; color: {tokens.primary_text};
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#successPill {{
            background: {tokens.success}; color: #ffffff;
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#pausedPill {{
            background: {tokens.warning}; color: #ffffff;
            border-radius: 10px; padding: 3px 10px; font-size: 12px;
            font-weight: 700;
        }}
        QLabel#secondary {{ color: {tokens.muted}; }}
        QLabel#insightValue {{
            color: {tokens.text}; font-size: {DESIGN.font_body_lg}px; font-weight: 700;
        }}
        QLabel#settingsRowTitle {{ color: {tokens.text}; font-weight: 700; }}

"""


def _control_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Buttons and segmented controls */
        QPushButton {{
            background: {tokens.surface}; color: {tokens.text};
            border: 1px solid {tokens.border}; border-radius: {DESIGN.radius_sm}px;
            min-height: 20px; padding: 7px 13px; font-weight: 600;
        }}
        QPushButton:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QPushButton:pressed {{ background: {tokens.primary_soft}; }}
        QPushButton:focus {{ border-color: {tokens.focus_ring}; }}
        QPushButton:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QPushButton#primary {{
            background: {tokens.primary}; color: {tokens.primary_text};
            border-color: {tokens.primary};
        }}
        QPushButton#primary:hover {{
            background: {tokens.primary_hover}; color: {tokens.primary_text};
            border-color: {tokens.primary_hover};
        }}
        QPushButton#primary:pressed {{
            background: {tokens.primary_pressed}; color: {tokens.primary_text};
            border-color: {tokens.primary_pressed};
        }}
        QPushButton#primary:focus {{ border-color: {tokens.focus_ring}; }}
        QPushButton#ghost {{
            background: transparent; border-color: transparent; color: {tokens.muted};
        }}
        QPushButton#ghost:hover {{ background: {tokens.surface_hover}; color: {tokens.text}; }}
        QPushButton#disclosureButton {{
            background: transparent; color: {tokens.muted}; border-color: transparent;
            text-align: left; padding: 6px 4px;
        }}
        QPushButton#disclosureButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QPushButton#danger {{
            background: transparent; color: {tokens.danger}; border-color: {tokens.separator};
        }}
        QPushButton#danger:hover {{ background: {tokens.surface_hover}; border-color: {tokens.danger}; }}
        QPushButton#iconButton {{
            background: transparent; border: 0; padding: 0;
            min-width: {DESIGN.control_height_sm}px; max-width: {DESIGN.control_height_sm}px;
            min-height: {DESIGN.control_height_sm}px; max-height: {DESIGN.control_height_sm}px;
            font-size: 18px; font-weight: 600;
        }}
        QPushButton#iconButton:hover {{ background: {tokens.primary_soft}; }}
        QPushButton#iconButton:focus {{
            border: 1px solid {tokens.focus_ring}; border-radius: {DESIGN.radius_sm}px;
        }}
        QPushButton#themeSwatch {{
            background: {tokens.surface}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_md}px; padding: 5px;
        }}
        QPushButton#themeSwatch:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QPushButton#themeSwatch:checked {{
            background: {tokens.primary_soft}; border: 2px solid {tokens.primary};
        }}
        QPushButton#themeSwatch:focus {{ border-color: {tokens.focus_ring}; }}
        QFrame#segmentedControl {{
            background: {tokens.surface_alt}; border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_sm}px;
        }}
        QFrame#segmentedControl QPushButton,
        QPushButton#segmentButton, QFrame#segmentedControl QRadioButton,
        QRadioButton#segmentButton {{
            background: transparent; color: {tokens.muted}; border: 1px solid transparent;
            border-radius: {DESIGN.radius_xs}px; padding: 5px 12px; min-height: 22px;
        }}
        QFrame#segmentedControl QPushButton:hover,
        QPushButton#segmentButton:hover, QFrame#segmentedControl QRadioButton:hover,
        QRadioButton#segmentButton:hover {{
            background: {tokens.surface_hover}; color: {tokens.text};
        }}
        QFrame#segmentedControl QPushButton:checked,
        QPushButton#segmentButton:checked, QFrame#segmentedControl QRadioButton:checked,
        QRadioButton#segmentButton:checked {{
            background: {tokens.surface_elevated}; color: {tokens.primary};
            border-color: {tokens.separator};
        }}
        QFrame#segmentedControl QPushButton:focus,
        QPushButton#segmentButton:focus, QFrame#segmentedControl QRadioButton:focus,
        QRadioButton#segmentButton:focus {{ border-color: {tokens.focus_ring}; }}
        QFrame#segmentedControl QRadioButton::indicator,
        QRadioButton#segmentButton::indicator {{ width: 0; height: 0; }}
        QDialog#quickPanel QRadioButton#segmentButton {{
            padding-left: 5px; padding-right: 5px;
        }}
        QComboBox[roundedSelector="true"],
        QDateEdit[roundedSelector="true"],
        QPushButton[roundedSelector="true"] {{
            background: {tokens.input}; color: {tokens.text};
            border: 1px solid {tokens.border};
            padding: 0 42px 0 14px;
        }}
        QComboBox[roundedSelector="true"][selectorDensity="large"],
        QDateEdit[roundedSelector="true"][selectorDensity="large"],
        QPushButton[roundedSelector="true"][selectorDensity="large"] {{
            border-radius: {DESIGN.radius_md}px;
            min-height: 46px; max-height: 46px;
            font-size: {DESIGN.font_body_lg}px;
        }}
        QComboBox[roundedSelector="true"][selectorDensity="compact"],
        QDateEdit[roundedSelector="true"][selectorDensity="compact"],
        QPushButton[roundedSelector="true"][selectorDensity="compact"] {{
            border-radius: 10px;
            min-height: 38px; max-height: 38px;
            font-size: {DESIGN.font_body}px;
        }}
        QPushButton[roundedSelector="true"] {{ text-align: left; }}
        QComboBox[roundedSelector="true"]:hover,
        QDateEdit[roundedSelector="true"]:hover,
        QPushButton[roundedSelector="true"]:hover {{
            background: {tokens.surface_hover}; border-color: {tokens.border_strong};
        }}
        QComboBox[roundedSelector="true"]:focus,
        QDateEdit[roundedSelector="true"]:focus,
        QPushButton[roundedSelector="true"]:focus {{
            border-color: {tokens.focus_ring};
        }}
        QComboBox[roundedSelector="true"]:disabled,
        QDateEdit[roundedSelector="true"]:disabled,
        QPushButton[roundedSelector="true"]:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QComboBox[roundedSelector="true"]::drop-down,
        QDateEdit[roundedSelector="true"]::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right;
            width: 38px; border: 0; background: transparent;
        }}
        QComboBox[roundedSelector="true"]::down-arrow,
        QDateEdit[roundedSelector="true"]::down-arrow {{
            image: none; width: 10px; height: 10px;
        }}
        QDateEdit[roundedSelector="true"]::up-button,
        QDateEdit[roundedSelector="true"]::down-button {{
            width: 0; height: 0; border: 0; background: transparent;
        }}
        QFrame#focusItemSelectorPopup, QFrame#roundedSelectorPopup {{
            background: transparent; border: 0;
        }}
        QFrame#roundedSelectorPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QFrame#focusItemSelectorPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border};
            border-radius: {DESIGN.radius_md}px;
        }}
        QListView#focusItemSelectorPopupView, QListView#roundedSelectorPopupView {{
            background: transparent; color: {tokens.text}; border: 0;
            padding: 6px; outline: 0;
            selection-background-color: transparent;
            selection-color: {tokens.text};
        }}
        QListView#focusItemSelectorPopupView::item,
        QListView#roundedSelectorPopupView::item {{
            min-height: 34px; padding: 4px 10px;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QListView#focusItemSelectorPopupView::item:selected,
        QListView#roundedSelectorPopupView::item:selected {{
            background: {tokens.primary_soft}; color: {tokens.text};
        }}
        QFrame#roundedTimePickerPopup {{ background: transparent; border: 0; }}
        QFrame#roundedTimePickerPopupSurface {{
            background: {tokens.surface_elevated};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QLabel#selectorPopupHeader {{
            color: {tokens.muted}; font-size: {DESIGN.font_caption}px;
            font-weight: 600; padding: 2px 4px;
        }}
        QListWidget#roundedTimePickerList {{
            background: transparent; color: {tokens.text}; border: 0;
            outline: 0; padding: 3px;
            selection-background-color: {tokens.primary_soft};
            selection-color: {tokens.text};
        }}
        QListWidget#roundedTimePickerList::item {{
            min-height: 32px; border-radius: {DESIGN.radius_sm}px;
        }}
        QWidget#themedCalendarPopup {{ background: transparent; border: 0; }}
        QScrollArea#themedCalendarScroll,
        QScrollArea#themedCalendarScroll QWidget#qt_scrollarea_viewport {{
            background: transparent; border: 0;
        }}
        QCalendarWidget#themedCalendar {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong};
            border-radius: {DESIGN.radius_md}px;
        }}
        QCalendarWidget#themedCalendar QWidget#qt_calendar_navigationbar {{
            background: {tokens.surface_alt};
            border-top-left-radius: {DESIGN.radius_md}px;
            border-top-right-radius: {DESIGN.radius_md}px;
        }}
        QCalendarWidget#themedCalendar QToolButton {{
            background: transparent; color: {tokens.text}; border: 0;
            border-radius: {DESIGN.radius_sm}px; padding: 5px;
        }}
        QCalendarWidget#themedCalendar QToolButton:hover {{
            background: {tokens.surface_hover};
        }}
        QCalendarWidget#themedCalendar QAbstractItemView {{
            background: {tokens.surface_elevated}; color: {tokens.text}; border: 0;
            border-bottom-left-radius: {DESIGN.radius_md}px;
            border-bottom-right-radius: {DESIGN.radius_md}px;
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}

"""


def _input_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Inputs */
        QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox, QListWidget,
        QTableWidget, QTextEdit, QPlainTextEdit {{
            background: {tokens.input}; color: {tokens.text};
            border: 1px solid {tokens.border}; border-radius: {DESIGN.radius_sm}px;
            padding: 6px 8px; min-height: 22px;
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus,
        QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QTextEdit:focus,
        QPlainTextEdit:focus {{
            border-color: {tokens.focus_ring};
        }}
        QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
        QTimeEdit:disabled, QSpinBox:disabled, QTextEdit:disabled,
        QPlainTextEdit:disabled {{
            background: {tokens.surface_alt}; color: {tokens.disabled};
            border-color: {tokens.separator};
        }}
        QComboBox QAbstractItemView {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            selection-background-color: {tokens.primary};
            selection-color: {tokens.primary_text};
        }}
        QScrollArea#focusPanelScroll,
        QScrollArea#focusPanelScroll > QWidget > QWidget {{
            background: transparent; border: 0;
        }}
        QTableWidget {{
            alternate-background-color: {tokens.surface_alt};
            gridline-color: transparent; border: 0;
        }}
        QTableWidget#sessionDataTable {{
            background: {tokens.surface}; alternate-background-color: {tokens.surface};
            selection-background-color: transparent; selection-color: {tokens.text};
            gridline-color: transparent; border: 0; border-radius: {DESIGN.radius_sm}px;
            padding: 0; outline: 0;
        }}
        QTableWidget#sessionDataTable::item {{
            background: transparent; border: 0; padding: 4px 8px;
        }}
        QHeaderView::section {{
            background: {tokens.surface_alt}; color: {tokens.muted};
            border: 0; border-bottom: 1px solid {tokens.separator};
            padding: 10px 8px; font-weight: 600;
        }}
        QTableWidget#sessionDataTable QHeaderView::section {{
            background: {tokens.surface}; color: {tokens.muted};
            border: 0; border-bottom: 1px solid {tokens.separator};
            padding: 8px; font-weight: 600;
        }}
        QProgressBar {{
            background: {tokens.border}; color: {tokens.text};
            border: 0; border-radius: 5px;
            min-height: 10px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {tokens.primary}; border-radius: 4px; }}
        QSlider::groove:horizontal {{
            height: 6px; background: {tokens.primary_soft}; border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            width: 16px; margin: -5px 0; background: {tokens.primary};
            border: 2px solid {tokens.surface}; border-radius: 8px;
        }}

"""


def _floating_style_sheet(tokens: ThemeTokens) -> str:
    return f"""        /* Floating surfaces */
        QMenu {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong}; border-radius: {DESIGN.radius_md}px;
            padding: 6px;
        }}
        QMenu::item {{
            background: transparent; padding: 9px 32px 9px 34px;
            border-radius: {DESIGN.radius_sm}px;
        }}
        QMenu::item:selected {{
            background: {tokens.primary_soft}; color: {tokens.text};
        }}
        QMenu::item:disabled {{ color: {tokens.disabled}; }}
        QMenu::separator {{
            height: 1px; background: {tokens.separator}; margin: 5px 8px;
        }}
        QToolTip {{
            background: {tokens.surface_elevated}; color: {tokens.text};
            border: 1px solid {tokens.border_strong}; border-radius: 6px; padding: 6px;
        }}
        QStatusBar {{ background: {tokens.surface}; color: {tokens.text}; }}
        QScrollBar:vertical {{
            background: transparent; width: 10px; margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {tokens.border_strong}; min-height: 28px; border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {tokens.muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent; height: 10px; margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {tokens.border_strong}; min-width: 28px; border-radius: 4px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QCheckBox, QRadioButton {{ spacing: 8px; }}
        QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
        /* Segmented radio buttons are text-only choices.  Keep this override
           after the generic radio style so the native indicator cannot leak
           back in through QSS source-order precedence. */
        QRadioButton#segmentButton {{ spacing: 0px; }}
        QRadioButton#segmentButton::indicator {{
            width: 0px; height: 0px; margin: 0px; padding: 0px;
            image: none; background: transparent; border: none;
        }}
    """
