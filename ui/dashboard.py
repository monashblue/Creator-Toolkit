"""Halaman Dashboard."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_LICENSE, APP_NAME, APP_VERSION
from ui.components.buttons import AppButton
from ui.components.cards import Card, CardGrid, EmptyState, ToolCard
from ui.components.recent_list import RecentList
from ui.icons import make_icon
from ui.recent_model import RowInfo
from ui.registry import CATEGORIES, get_page, tool_pages
from ui.theme import current_palette


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


class Dashboard(QScrollArea):
    """Sambutan, pencarian alat, akses cepat, kategori, dan berkas terbaru."""

    open_page = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("PageRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        title = QLabel(f"Selamat datang di {APP_NAME}")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Semua alat kreator dalam satu aplikasi. Berkas Anda diproses langsung di komputer ini."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Cari alat, misalnya: QR, latar belakang, ukuran")
        self._search.setClearButtonEnabled(True)
        self._search.setAccessibleName("Cari alat")
        self._search.setMaximumWidth(520)
        self._search_action = self._search.addAction(
            make_icon("search", current_palette()["muted"]),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        layout.addWidget(_section_title("Akses Cepat"))
        self._quick_grid = CardGrid(min_card_width=230)
        for tool in tool_pages():
            card = ToolCard(tool.page_id, tool.icon, tool.title, tool.description, tool.keywords)
            card.clicked.connect(lambda pid=tool.page_id: self.open_page.emit(pid))
            self._quick_grid.add_card(card)
        layout.addWidget(self._quick_grid)

        self._no_results = EmptyState(
            "search",
            "Alat tidak ditemukan",
            "Coba kata kunci lain, misalnya: QR, latar belakang, ukuran, atau format.",
        )
        self._no_results.hide()
        layout.addWidget(self._no_results)

        layout.addWidget(_section_title("Kategori Fitur"))
        category_grid = CardGrid(min_card_width=320)
        for category in CATEGORIES:
            category_grid.add_card(self._build_category_card(category.title, category.description, category.tool_ids))
        layout.addWidget(category_grid)

        layout.addWidget(_section_title("Berkas Terakhir Diproses"))
        recent_card = Card()
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(8, 8, 8, 8)
        self._recent_list = RecentList(interactive=False)
        self._recent_empty = EmptyState(
            "clock",
            "Belum ada berkas yang diproses",
            "Hasil kerja Anda akan tampil di sini setelah Anda memakai salah satu alat.",
        )
        recent_layout.addWidget(self._recent_list)
        recent_layout.addWidget(self._recent_empty)
        self._recent_list.hide()
        layout.addWidget(recent_card)

        layout.addStretch(1)
        footer = QLabel(f"{APP_NAME} v{APP_VERSION}  |  Lisensi {APP_LICENSE}")
        footer.setObjectName("VersionLabel")
        layout.addWidget(footer)

        self.setWidget(root)

    def _build_category_card(self, title: str, description: str, tool_ids: tuple[str, ...]) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        text_label = QLabel(description)
        text_label.setObjectName("CardText")
        text_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(text_label)

        row = QHBoxLayout()
        row.setSpacing(6)
        for tool_id in tool_ids:
            button = AppButton(get_page(tool_id).title, "ghost")
            button.clicked.connect(lambda checked=False, pid=tool_id: self.open_page.emit(pid))
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return card

    def set_recent(self, rows: list[RowInfo] | None) -> None:
        """Menampilkan berkas terakhir diproses. None atau daftar kosong menampilkan keadaan kosong."""
        if rows:
            self._recent_list.set_rows(rows)
        self._recent_list.setVisible(bool(rows))
        self._recent_empty.setVisible(not rows)

    def _on_search(self, text: str) -> None:
        query = text.strip()
        self._quick_grid.set_filter(lambda card: card.matches(query))  # type: ignore[attr-defined]
        has_results = self._quick_grid.visible_count() > 0
        self._quick_grid.setVisible(has_results)
        self._no_results.setVisible(not has_results)

    def refresh_icons(self) -> None:
        self._search_action.setIcon(make_icon("search", current_palette()["muted"]))
