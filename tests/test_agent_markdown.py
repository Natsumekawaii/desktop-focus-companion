"""Real Markdown tables, safe imports, wrapping and live theme changes."""

from math import ceil

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor, QTextDocument, QTextTable

from app.core.theme import COLOR_THEMES, get_theme_manager
from app.ui.agent_page import AgentPage, SafeMarkdown

TABLE = """## 每日

| 日期 | 时长 | 记录 |
| :--- | ---: | :--- |
| 11-02 周一 | 95 分 | 学习 35 分（08:20–08:55，复习课程笔记，ID 7）；深度工作 60 分（13:10–14:10，整理产品路线图，ID 8） |
| 11-03 周二 | 115 分 | 深度工作 75 分；阅读 40 分 |
| 11-04 周三 | 215 分 | 阅读 45 分；深度工作 90 分；学习 50 分；健身 30 分 |
| 11-05 今天 | 0 分 | 无记录（不等于没做事，只是没记录） |

## 项目占比

- **深度工作**：225 分
"""


def tables(view):
    return [frame for frame in view.document().rootFrame().childFrames() if isinstance(frame, QTextTable)]


def cell_text(table, row, column):
    cell = table.cellAt(row, column)
    cursor = cell.firstCursorPosition()
    cursor.setPosition(cell.lastPosition(), QTextCursor.MoveMode.KeepAnchor)
    return cursor.selectedText()


@pytest.mark.parametrize("theme", COLOR_THEMES)
def test_table_layout_colors_wrapping_and_resize(qt_application, theme):
    get_theme_manager().set_theme(theme)
    view = SafeMarkdown()
    view.show_markdown(TABLE)
    view.show()
    table, = tables(view)
    assert (table.rows(), table.columns()) == (5, 3)
    assert cell_text(table, 1, 0) == "11-02 周一"
    assert "ID 8" in cell_text(table, 1, 2)
    assert "|" not in view.toPlainText()
    assert table.format().headerRowCount() == 1
    assert table.format().cellPadding() == 8
    tokens = get_theme_manager().tokens
    assert table.cellAt(0, 0).format().background().color().name() == tokens.primary_soft.lower()
    assert table.cellAt(1, 0).format().background().color().name() == tokens.surface.lower()
    for width in (900, 600, 360, 700):
        view.resize(width, view.height())
        qt_application.processEvents()
        assert view.horizontalScrollBar().maximum() == 0
        assert view.document().size().width() <= view.viewport().width() + 1
        assert view.viewport().height() >= ceil(view.document().size().height())


def test_streamed_table_matches_loaded_history_and_theme_refresh(qt_application):
    page = AgentPage()
    view = page._views
    for end in range(1, len(TABLE), 23):
        page.show_turns("chat", [{"id": "reply", "answer": TABLE[:end]}], True)
    page.show_turns("chat", [{"id": "reply", "answer": TABLE}], False)
    answer = view["reply"].answer
    original = answer.toPlainText()
    for theme in COLOR_THEMES:
        get_theme_manager().set_theme(theme)
        table, = tables(answer)
        assert answer.toPlainText() == original
        assert table.cellAt(0, 0).format().background().color().name() == get_theme_manager().tokens.primary_soft.lower()
    restored = SafeMarkdown()
    restored.show_markdown(TABLE)
    assert restored.toPlainText() == original
    assert (tables(restored)[0].rows(), tables(restored)[0].columns()) == (5, 3)
    assert view["reply"].content == TABLE


def test_code_pipes_raw_html_and_resources_stay_safe(qt_application):
    view = SafeMarkdown()
    view.show_markdown("```text\n| a | b |\n|---|---|\n| c | d |\n```\n\n`a | b`\n\n<table><tr><td>raw</td></tr></table>\n<img src='https://example.com/tracker.png'>")
    assert not tables(view)
    assert "| a | b |" in view.toPlainText()
    assert not view.openLinks() and not view.openExternalLinks()
    for address in ("https://example.com/tracker.png", "file:///private.txt", "data:image/png;base64,abc"):
        assert view.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(address)) is None
    view.show_markdown("| Label | Detail |\n|---|---|\n| a \\| b | **bold** and `code` |")
    table, = tables(view)
    assert table.columns() == 2 and cell_text(table, 1, 0) == "a | b"


def test_extreme_width_table_remains_scrollable_not_clipped(qt_application):
    view = SafeMarkdown()
    view.resize(350, 200)
    header = "|" + "|".join("column" for _ in range(20)) + "|\n"
    view.show_markdown(header + "|" + "|".join("---" for _ in range(20)) + "|\n" + header)
    view.show()
    qt_application.processEvents()
    assert view.horizontalScrollBar().maximum() > 0
    assert view.horizontalScrollBar().isVisible()
    assert view.viewport().height() >= ceil(view.document().size().height())
