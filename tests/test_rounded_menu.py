"""Focused rendering and behavior tests for the shared rounded context menu."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtTest import QTest

from app.core.theme import (
    COLOR_THEMES,
    DEFAULT_COLOR_THEME,
    THEME_TOKENS,
    get_theme_manager,
)
from app.ui.rounded_menu import RoundedMenu


def test_rounded_menu_has_antialiased_transparent_corners_and_a_soft_shadow(
    qt_application,
) -> None:
    menu = RoundedMenu()
    menu.addAction("Focus Center")
    menu.addSeparator()
    menu.addAction("Settings")
    menu.resize(220, 120)
    menu.show()
    qt_application.processEvents()

    try:
        assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert menu.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        assert not menu.autoFillBackground()
        assert menu.mask().isEmpty()
        assert menu.minimumWidth() == 150
        assert all(
            menu.actionGeometry(action).height() >= 40
            for action in menu.actions()
            if not action.isSeparator()
        )

        image = menu.grab().toImage()
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(image.width() - 1, 0).alpha() == 0
        assert image.pixelColor(0, image.height() - 1).alpha() == 0
        assert image.pixelColor(image.width() - 1, image.height() - 1).alpha() == 0
        assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() > 0
        edge_alphas = {
            image.pixelColor(x, y).alpha()
            for y in range(min(24, image.height()))
            for x in range(min(24, image.width()))
        }
        assert any(0 < alpha < 255 for alpha in edge_alphas)
    finally:
        menu.close()


def test_rounded_menu_keeps_qmenu_actions_and_refreshes_with_every_theme(
    qt_application,
) -> None:
    manager = get_theme_manager()
    original_theme = manager.theme_name
    menu = RoundedMenu()
    focus_action = menu.addAction("Focus Center")
    triggered: list[bool] = []
    focus_action.triggered.connect(lambda: triggered.append(True))

    try:
        for theme_name in COLOR_THEMES:
            manager.set_theme(theme_name)
            qt_application.processEvents()
            assert THEME_TOKENS[theme_name].primary_soft in menu.styleSheet()
            assert THEME_TOKENS[theme_name].primary_pressed in menu.styleSheet()
            assert "background: transparent" in menu.styleSheet()

        menu.popup(qt_application.primaryScreen().availableGeometry().center())
        qt_application.processEvents()
        QTest.keyClick(menu, Qt.Key.Key_Down)
        QTest.keyClick(menu, Qt.Key.Key_Return)
        assert triggered == [True]
    finally:
        menu.close()
        manager.set_theme(original_theme or DEFAULT_COLOR_THEME)


def test_rounded_menu_uses_compact_content_aware_width(qt_application) -> None:
    chinese_menu = RoundedMenu()
    chinese_menu.addAction("专注中心")
    chinese_menu.addAction("显示桌宠")
    english_menu = RoundedMenu()
    english_menu.addAction("Focus Center")
    longest_action = english_menu.addAction("Show Companion")

    try:
        assert chinese_menu.sizeHint().width() == 150

        english_width = english_menu.sizeHint().width()
        longest_text_width = english_menu.fontMetrics().horizontalAdvance(
            "Show Companion"
        )
        assert english_width == max(
            english_menu._minimum_width,
            longest_text_width + english_menu._width_reserve,
        )

        english_menu.resize(english_menu.sizeHint())
        english_menu.show()
        qt_application.processEvents()
        action_width = english_menu.actionGeometry(longest_action).width()
        assert action_width - longest_text_width >= 18
    finally:
        chinese_menu.close()
        english_menu.close()


def test_rounded_menu_centers_one_aligned_icon_and_text_column(
    qt_application,
) -> None:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor("#7C5CFC"))
    icon = QIcon(pixmap)
    menu = RoundedMenu()
    actions = [
        menu.addAction(icon, "Focus Center"),
        menu.addAction(icon, "Settings"),
        menu.addAction(icon, "Show Companion"),
        menu.addAction(icon, "Exit"),
    ]
    menu.resize(menu.sizeHint())
    menu.show()
    qt_application.processEvents()

    try:
        layouts = [menu._action_content_layout(action) for action in actions]
        icon_lefts = {
            round(icon_rect.left(), 3)
            for icon_rect, _text_rect in layouts
            if icon_rect is not None
        }
        text_lefts = {round(text_rect.left(), 3) for _icon_rect, text_rect in layouts}
        assert len(icon_lefts) == 1
        assert len(text_lefts) == 1

        icon_rect, _text_rect = layouts[2]
        assert icon_rect is not None
        block_width = (
            menu._icon_size
            + menu._icon_text_gap
            + menu._longest_visible_text_width()
        )
        assert abs(
            icon_rect.left() + block_width / 2 - menu._surface_rect().center().x()
        ) < 0.01

        menu.setActiveAction(actions[0])
        menu.repaint()
        qt_application.processEvents()
        image = menu.grab().toImage()
        item_rect = menu._item_rect(actions[0])
        sample = image.pixelColor(
            int(item_rect.right() - 5),
            int(item_rect.center().y()),
        )
        assert sample == QColor(get_theme_manager().tokens.primary_soft)
    finally:
        menu.close()
