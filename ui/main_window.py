"""Jendela utama."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from app.constants import APP_NAME
from core.database import STATUS_SUCCESS, VALID_STATUSES, HistoryError, NewEntry
from core.logger import get_logger
from modules.background_remover.interface import BackgroundRemoverPage
from modules.qr_generator.interface import QRGeneratorPage
from ui.dashboard import Dashboard
from ui.pages import AboutPage, ComingSoonPage, RecentProjectsPage, SettingsPage
from ui.recent_model import load_rows
from ui.registry import PAGES, get_page
from ui.sidebar import Sidebar
from ui.theme import ThemeManager

if TYPE_CHECKING:
    from app.application import AppContext

log = get_logger("ui.main_window")

INITIAL_SIZE = (1200, 800)
MINIMUM_SIZE = (900, 650)
DASHBOARD_RECENT = 5


class MainWindow(QMainWindow):
    """Sidebar di kiri dan area konten bertumpuk di kanan."""

    def __init__(self, context: "AppContext", theme: ThemeManager) -> None:
        super().__init__()
        self._context = context
        self.setWindowTitle(APP_NAME)
        self.resize(*INITIAL_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._stack = QStackedWidget()
        layout.addWidget(self._sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._page_index: dict[str, int] = {}
        self._build_pages(context, theme)

        self._sidebar.navigate.connect(self.navigate)
        theme.theme_changed.connect(self._refresh_icons)
        self.navigate("dashboard")

    def _add_page(self, page_id: str, widget: QWidget) -> None:
        self._page_index[page_id] = self._stack.addWidget(widget)

    def _build_pages(self, context: "AppContext", theme: ThemeManager) -> None:
        dashboard = Dashboard()
        dashboard.open_page.connect(self.navigate)
        self._dashboard = dashboard
        self._add_page("dashboard", dashboard)

        for page in PAGES:
            if page.page_id in ("dashboard", "settings", "about"):
                continue
            if page.page_id == "qr":
                qr_page = QRGeneratorPage(context)
                qr_page.exported.connect(self._on_qr_exported)
                self._add_page("qr", qr_page)
                continue
            if page.page_id == "background":
                background_page = BackgroundRemoverPage(context)
                background_page.processed.connect(self._on_background_processed)
                self._add_page("background", background_page)
                continue
            if page.page_id == "recent":
                self._recent_page = RecentProjectsPage(context)
                self._add_page("recent", self._recent_page)
                continue
            coming_soon = ComingSoonPage(page.title, page.description, page.planned)
            coming_soon.back_requested.connect(lambda: self.navigate("dashboard"))
            self._add_page(page.page_id, coming_soon)

        self._add_page("settings", SettingsPage(context, theme))
        self._add_page("about", AboutPage())

    def navigate(self, page_id: str) -> None:
        index = self._page_index.get(page_id)
        if index is None:
            log.warning("Halaman %r tidak ditemukan.", page_id)
            return
        self._stack.setCurrentIndex(index)
        self._sidebar.set_current(page_id)
        log.info("Membuka halaman: %s", get_page(page_id).title)
        if page_id in ("dashboard", "recent"):
            self._refresh_history_views()  # juga memeriksa ulang berkas yang mungkin sudah dihapus

    def _on_qr_exported(self, path: str) -> None:
        self._record_history([NewEntry(get_page("qr").title, None, path, STATUS_SUCCESS)])

    def _on_background_processed(self, entries: list) -> None:
        title = get_page("background").title
        records = [
            NewEntry(title, entry.get("input"), entry.get("output"), entry["status"])
            for entry in entries
            if isinstance(entry, dict) and entry.get("status") in VALID_STATUSES
        ]
        self._record_history(records)

    def _record_history(self, records: list[NewEntry]) -> None:
        history = self._context.history
        if history is not None and records:
            try:
                history.add_many(records)
            except (HistoryError, ValueError):
                log.exception("Gagal mencatat riwayat.")
        self._refresh_history_views()

    def _refresh_history_views(self) -> None:
        self._recent_page.refresh()
        self._dashboard.set_recent(load_rows(self._context.history, DASHBOARD_RECENT))

    def _refresh_icons(self, _theme_name: str) -> None:
        for widget in self.findChildren(QWidget):
            refresh = getattr(widget, "refresh_icons", None)
            if callable(refresh):
                refresh()
