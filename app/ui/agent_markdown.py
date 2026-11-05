"""Safe, theme-aware GitHub Markdown for streamed and stored agent replies."""

from __future__ import annotations

from math import ceil
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QFont,
    QResizeEvent,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFrame,
    QTextFrameFormat,
    QTextLength,
    QTextOption,
    QTextTable,
)
from PySide6.QtWidgets import QFrame, QSizePolicy, QTextBrowser, QWidget

from app.core.theme import get_theme_manager


def _tables(frame: QTextFrame) -> list[QTextTable]:
    result: list[QTextTable] = []
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            result.append(child)
        result.extend(_tables(child))
    return result


class SafeMarkdown(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QTextBrowser { background: transparent; border: 0; padding: 0; }")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Ordinary tables wrap; exceptionally wide tables remain accessible.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._fitting = False
        get_theme_manager().theme_changed.connect(self._restyle)

    def loadResource(self, resource_type: int, name: QUrl | str) -> Any:
        return None  # No remote images, files, stylesheets, or embedded HTML.

    def show_markdown(self, value: str) -> None:
        self.document().setMarkdown(
            value,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML,
        )
        self._restyle()

    def _restyle(self, *_: Any) -> None:
        document = self.document()
        tokens = get_theme_manager().tokens
        option = document.defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(option)
        document.setDocumentMargin(8)
        block = document.begin()
        while block.isValid():
            cursor = QTextCursor(block)
            formatting = block.blockFormat()
            in_table = cursor.currentTable() is not None
            heading = formatting.headingLevel()
            formatting.setTopMargin(14 if heading else 0)
            formatting.setBottomMargin(8 if heading else 0 if in_table else 8)
            formatting.setLineHeight(140, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            cursor.setBlockFormat(formatting)
            if heading:
                # Keep imported Markdown headings proportional to chat body text.
                font = document.defaultFont()
                base = font.pointSizeF()
                if base <= 0:
                    base = self.fontInfo().pointSizeF()
                char_format = QTextCharFormat()
                char_format.setFontPointSize(base * (1.4 if heading == 1 else 1.2))
                char_format.setFontWeight(QFont.Weight.DemiBold)
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.mergeCharFormat(char_format)
            block = block.next()

        for table in _tables(document.rootFrame()):
            table_format = table.format()
            table_format.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
            table_format.setBorder(1)
            table_format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            table_format.setBorderBrush(QColor(tokens.border))
            table_format.setBorderCollapse(True)
            table_format.setCellSpacing(0)
            table_format.setCellPadding(8)
            table_format.setTopMargin(6)
            table_format.setBottomMargin(12)
            table_format.setHeaderRowCount(1)
            # Give descriptive columns room without letting long unbroken text
            # dictate the document width. All sizing uses already-parsed cells.
            weights = []
            for column in range(table.columns()):
                longest = 80
                for row in range(table.rows()):
                    cell = table.cellAt(row, column)
                    cursor = cell.firstCursorPosition()
                    cursor.setPosition(cell.lastPosition(), QTextCursor.MoveMode.KeepAnchor)
                    longest = max(longest, min(360, self.fontMetrics().horizontalAdvance(cursor.selectedText()) + 16))
                    cell_format = cell.format().toTableCellFormat()
                    cell_format.setBackground(QColor(tokens.primary_soft if row == 0 else tokens.surface))
                    cell_format.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignTop)
                    cell_format.setBorder(0)
                    cell_format.setBottomBorder(1)
                    cell_format.setBottomBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
                    cell_format.setBottomBorderBrush(QColor(tokens.border if row == 0 else tokens.separator))
                    cell.setFormat(cell_format)
                weights.append(longest)
            table_format.setColumnWidthConstraints([
                QTextLength(QTextLength.Type.PercentageLength, 100 * weight / sum(weights))
                for weight in weights
            ])
            table.setFormat(table_format)
        self._fit()

    def _fit(self) -> None:
        if self._fitting:
            return
        self._fitting = True
        try:
            self.document().setTextWidth(max(150, self.viewport().width()))
            scrollbar = self.horizontalScrollBar()
            extra = scrollbar.sizeHint().height() if scrollbar.maximum() > 0 else 0
            self.setFixedHeight(max(40, ceil(self.document().size().height()) + extra + 4))
        finally:
            self._fitting = False

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()
