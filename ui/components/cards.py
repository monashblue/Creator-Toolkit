"""Kartu, keadaan kosong, dan grid kartu responsif."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from ui.components.buttons import AppButton
from ui.icons import make_pixmap
from ui.theme import current_palette


class Card(QFrame):
    """Wadah dengan latar permukaan, border halus, dan sudut membulat."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def _passive(label: QLabel) -> QLabel:
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    return label


class ToolCard(QFrame):
    """Kartu alat yang dapat diklik atau dipilih dengan keyboard."""

    clicked = Signal()

    def __init__(
        self,
        page_id: str,
        icon_name: str,
        title: str,
        description: str,
        keywords: tuple[str, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.page_id = page_id
        self._icon_name = icon_name
        self._search_text = " ".join([title, description, *keywords]).lower()

        self.setObjectName("ToolCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(150)
        self.setAccessibleName(title)
        self.setToolTip(description)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self._badge = _passive(QLabel())
        self._badge.setObjectName("IconBadge")
        self._badge.setFixedSize(44, 44)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = _passive(QLabel(title))
        title_label.setObjectName("CardTitle")
        text_label = _passive(QLabel(description))
        text_label.setObjectName("CardText")
        text_label.setWordWrap(True)

        layout.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        layout.addStretch(1)
        self.refresh_icons()

    def matches(self, query: str) -> bool:
        tokens = query.lower().split()
        return all(token in self._search_text for token in tokens)

    def refresh_icons(self) -> None:
        self._badge.setPixmap(make_pixmap(self._icon_name, current_palette()["accent_text"], 24))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class EmptyState(QWidget):
    """Tampilan kosong dengan ikon, judul, penjelasan, dan tombol aksi opsional."""

    action_clicked = Signal()

    def __init__(
        self,
        icon_name: str,
        title: str,
        message: str,
        action_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self.setObjectName("EmptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._badge = QLabel()
        self._badge.setObjectName("IconBadgeLarge")
        self._badge.setFixedSize(64, 64)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label = QLabel(message)
        message_label.setObjectName("Muted")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setWordWrap(True)

        layout.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(message_label)
        if action_text:
            button = AppButton(action_text, "secondary")
            button.clicked.connect(self.action_clicked.emit)
            layout.addSpacing(6)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        self._badge.setPixmap(make_pixmap(self._icon_name, current_palette()["accent_text"], 28))


class CardGrid(QWidget):
    """Grid yang menyesuaikan jumlah kolom dengan lebar dan dapat menyaring kartu."""

    def __init__(
        self, min_card_width: int = 240, spacing: int = 16, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._min_card_width = min_card_width
        self._spacing = spacing
        self._cards: list[QWidget] = []
        self._visible: dict[QWidget, bool] = {}
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)

    def add_card(self, card: QWidget) -> None:
        self._cards.append(card)
        self._visible[card] = True
        self._relayout()

    def set_filter(self, predicate: Callable[[QWidget], bool]) -> None:
        for card in self._cards:
            self._visible[card] = bool(predicate(card))
        self._relayout()

    def visible_count(self) -> int:
        return sum(1 for shown in self._visible.values() if shown)

    def _compute_columns(self) -> int:
        width = max(self.width(), 1)
        return max(1, (width + self._spacing) // (self._min_card_width + self._spacing))

    def resizeEvent(self, event) -> None:  # noqa: N802 (nama bawaan Qt)
        super().resizeEvent(event)
        if self._compute_columns() != self._columns:
            self._relayout()

    def _relayout(self) -> None:
        columns = self._compute_columns()
        for index in range(self._columns):
            self._grid.setColumnStretch(index, 0)
        for card in self._cards:
            self._grid.removeWidget(card)
        row = column = 0
        for card in self._cards:
            if self._visible[card]:
                self._grid.addWidget(card, row, column)
                card.show()
                column += 1
                if column >= columns:
                    column = 0
                    row += 1
            else:
                card.hide()
        for index in range(columns):
            self._grid.setColumnStretch(index, 1)
        self._columns = columns
