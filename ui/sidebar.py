"""Sidebar navigasi."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from app.constants import APP_NAME, APP_TAGLINE
from ui.icons import make_icon
from ui.registry import PageInfo, main_pages, other_pages
from ui.theme import current_palette

SIDEBAR_WIDTH = 230


class Sidebar(QFrame):
    """Menu navigasi kiri. Memancarkan sinyal navigate dengan page_id tujuan."""

    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)

        self._buttons: dict[str, QPushButton] = {}
        self._pages: dict[str, PageInfo] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(4)

        title = QLabel(APP_NAME)
        title.setObjectName("SidebarTitle")
        tagline = QLabel(APP_TAGLINE)
        tagline.setObjectName("SidebarTagline")
        tagline.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(tagline)
        layout.addSpacing(20)

        self._add_section(layout, "MENU UTAMA", main_pages())
        layout.addSpacing(16)
        self._add_section(layout, "LAINNYA", other_pages())
        layout.addStretch(1)
        self.refresh_icons()

    def _add_section(self, layout: QVBoxLayout, heading: str, pages: list[PageInfo]) -> None:
        label = QLabel(heading)
        label.setObjectName("SidebarSection")
        layout.addWidget(label)
        for page in pages:
            button = QPushButton(page.title)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(20, 20))
            button.setAccessibleName(page.title)
            button.clicked.connect(lambda checked=False, pid=page.page_id: self.navigate.emit(pid))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[page.page_id] = button
            self._pages[page.page_id] = page

    def set_current(self, page_id: str) -> None:
        button = self._buttons.get(page_id)
        if button is not None:
            button.setChecked(True)

    def refresh_icons(self) -> None:
        colors = current_palette()
        for page_id, button in self._buttons.items():
            button.setIcon(
                make_icon(self._pages[page_id].icon, colors["muted"], colors["accent_text"], 20)
            )
