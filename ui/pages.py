"""Halaman pendamping: halaman sementara, Pengaturan, dan Tentang."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

import PySide6
from PySide6.QtCore import Qt, QUrl, Signal, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QScrollArea,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_LICENSE, APP_NAME, APP_TAGLINE, APP_VERSION
from core.config_manager import set_default_output_directory
from core.logger import get_logger
from ui.components.buttons import AppButton
from ui.components.cards import Card, EmptyState
from ui.components.recent_list import RecentList
from ui.recent_model import load_rows
from ui.theme import ThemeManager

if TYPE_CHECKING:
    from app.application import AppContext

log = get_logger("ui.pages")


def _page_layout(page: QWidget, title: str, subtitle: str) -> QVBoxLayout:
    page.setObjectName("PageRoot")
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(32, 28, 32, 28)
    layout.setSpacing(16)
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)
    return layout


class ComingSoonPage(QWidget):
    """Halaman informatif untuk fitur yang belum tersedia.

    Satu-satunya tombol pada halaman ini, Kembali ke Dashboard, berfungsi penuh.
    """

    back_requested = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        planned: tuple[str, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = _page_layout(self, title, subtitle)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(10)

        badge = QLabel("SEGERA HADIR")
        badge.setObjectName("StatusBadge")
        card_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        heading = QLabel("Fitur ini sedang dikembangkan")
        heading.setObjectName("SectionTitle")
        explanation = QLabel(
            f"Halaman {title} belum memiliki fungsi pada versi ini. "
            "Tampilan ini hanya penanda tempat, tidak ada yang akan diproses."
        )
        explanation.setObjectName("CardText")
        explanation.setWordWrap(True)
        card_layout.addWidget(heading)
        card_layout.addWidget(explanation)

        if planned:
            planned_title = QLabel("Yang direncanakan")
            planned_title.setObjectName("CardTitle")
            card_layout.addSpacing(6)
            card_layout.addWidget(planned_title)
            for item in planned:
                line = QLabel(f"\u2022  {item}")
                line.setObjectName("CardText")
                line.setWordWrap(True)
                card_layout.addWidget(line)

        back_button = AppButton("Kembali ke Dashboard", "secondary")
        back_button.clicked.connect(self.back_requested.emit)
        card_layout.addSpacing(10)
        card_layout.addWidget(back_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addStretch(1)


def _setting_card(title: str, description: str, control: QWidget) -> tuple[Card, QLabel]:
    """Kartu pengaturan. Mengembalikan kartu dan label deskripsinya agar teks dapat diperbarui."""
    card = Card()
    row = QHBoxLayout(card)
    row.setContentsMargins(20, 16, 20, 16)
    row.setSpacing(16)
    text = QVBoxLayout()
    text.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("CardTitle")
    description_label = QLabel(description)
    description_label.setObjectName("CardText")
    description_label.setWordWrap(True)
    description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    text.addWidget(title_label)
    text.addWidget(description_label)
    row.addLayout(text, 1)
    row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return card, description_label


class SettingsPage(QWidget):
    """Pengaturan tema, folder keluaran bawaan, dan lokasi log."""

    def __init__(self, context: "AppContext", theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._theme = theme
        layout = _page_layout(self, "Pengaturan", "Atur tampilan dan lokasi penyimpanan aplikasi.")

        self._theme_combo = QComboBox()
        self._theme_combo.setAccessibleName("Tema aplikasi")
        self._theme_combo.addItem("Terang", "light")
        self._theme_combo.addItem("Gelap", "dark")
        index = self._theme_combo.findData(context.config.get("theme", "light"))
        self._theme_combo.setCurrentIndex(max(index, 0))
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_card, _ = _setting_card("Tema", "Pilih tampilan terang atau gelap.", self._theme_combo)
        layout.addWidget(theme_card)

        output_button = AppButton("Ubah folder...", "secondary")
        output_button.clicked.connect(self._choose_output_directory)
        output_card, self._output_description = _setting_card(
            "Folder keluaran bawaan", "", output_button
        )
        layout.addWidget(output_card)
        self._refresh_output_text()

        log_button = AppButton("Buka folder log", "secondary")
        log_button.clicked.connect(self._open_log_folder)
        log_card, _ = _setting_card(
            "Berkas log",
            f"Catatan teknis untuk pemecahan masalah tersimpan di: {context.paths.logs_dir}",
            log_button,
        )
        layout.addWidget(log_card)
        layout.addStretch(1)

    def _refresh_output_text(self) -> None:
        self._output_description.setText(str(self._context.config.get("output_directory", "")))

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, "Pengaturan", message)

    def _save_setting(self, key: str, value: object) -> bool:
        try:
            self._context.config.set(key, value)
        except OSError as exc:
            log.error("Gagal menyimpan pengaturan %s: %s", key, exc)
            self._warn(
                "Pengaturan tidak dapat disimpan. Periksa izin folder data aplikasi. "
                "Rincian teknis tersimpan di berkas log."
            )
            return False
        return True

    def _on_theme_changed(self, _index: int) -> None:
        name = self._theme_combo.currentData()
        if not self._theme.apply(name):
            self._warn("Tema tidak dapat dimuat. Rincian teknis tersimpan di berkas log.")
            return
        self._save_setting("theme", name)

    def _choose_output_directory(self) -> None:
        current = str(self._context.config.get("output_directory", ""))
        chosen = QFileDialog.getExistingDirectory(self, "Pilih folder keluaran bawaan", current)
        if not chosen:
            return
        try:
            set_default_output_directory(self._context.config, chosen)
        except OSError as exc:
            log.error("Gagal menyimpan folder keluaran bawaan: %s", exc)
            self._warn(
                "Pengaturan tidak dapat disimpan. Periksa izin folder data aplikasi. "
                "Rincian teknis tersimpan di berkas log."
            )
            return
        self._refresh_output_text()

    def _open_log_folder(self) -> None:
        folder = self._context.paths.logs_dir
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._warn(f"Folder log tidak dapat dibuka. Lokasinya: {folder}")


class RecentProjectsPage(QWidget):
    """Daftar berkas yang baru diproses, dengan deteksi berkas hilang dan pintasan membuka folder."""

    def __init__(self, context: "AppContext", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        layout = _page_layout(self, "Proyek Terbaru", "Berkas yang baru Anda proses beserta lokasinya.")
        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)

        self._list = RecentList(interactive=True)
        self._list.open_requested.connect(self._open_folder)
        scroll = QScrollArea()
        scroll.setObjectName("RecentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._list)
        self._empty = EmptyState(
            "clock",
            "Belum ada berkas yang diproses",
            "Hasil dari QR Code Generator dan Background Remover akan tampil di sini.",
        )
        self._unavailable = EmptyState(
            "info",
            "Riwayat tidak tersedia",
            "Riwayat tidak dapat dibuka sehingga daftar tidak bisa ditampilkan. "
            "Fitur lain tetap berfungsi. Rincian teknis ada di berkas log.",
        )
        card_layout.addWidget(scroll)
        card_layout.addWidget(self._empty)
        card_layout.addWidget(self._unavailable)
        layout.addWidget(card, 1)
        self._scroll = scroll
        self.refresh()

    def refresh(self) -> None:
        """Memuat ulang daftar dan memeriksa ulang keberadaan berkas."""
        try:
            limit = max(1, min(500, int(self._context.config.get("recent_projects_limit", 50))))
        except (TypeError, ValueError):
            limit = 50
        rows = load_rows(self._context.history, limit)
        self._unavailable.setVisible(rows is None)
        self._empty.setVisible(rows is not None and not rows)
        self._scroll.setVisible(bool(rows))
        if rows:
            self._list.set_rows(rows)

    def _open_folder(self, folder: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            QMessageBox.warning(self, "Proyek Terbaru", f"Folder tidak dapat dibuka: {folder}")


class AboutPage(QWidget):
    """Informasi aplikasi dan versi komponen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = _page_layout(self, f"Tentang {APP_NAME}", APP_TAGLINE)
        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(8)
        lines = [
            f"Versi aplikasi: {APP_VERSION}",
            f"Lisensi kode sumber: {APP_LICENSE}",
            f"Python: {platform.python_version()}",
            f"PySide6: {PySide6.__version__} (Qt {qVersion()})",
            "Aplikasi gratis dan sumber terbuka. Berkas Anda diproses secara lokal.",
        ]
        for line in lines:
            label = QLabel(line)
            label.setObjectName("CardText")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_layout.addWidget(label)
        layout.addWidget(card)
        layout.addStretch(1)
