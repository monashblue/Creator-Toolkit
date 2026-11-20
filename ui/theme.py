"""Pengelola tema terang dan gelap."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from core.logger import get_logger

log = get_logger("theme")

# Warna di sini dipakai untuk ikon dan palet Qt. Nilainya harus sama dengan berkas .qss
# (diperiksa oleh tests/test_styles.py). accent_text adalah warna aksen untuk teks dan ikon kecil
# di atas latar gelap atau lembut, agar kontrasnya memenuhi 4,5 banding 1.
PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#F6F7FB",
        "surface": "#FFFFFF",
        "text": "#1F2430",
        "muted": "#5F6679",
        "accent": "#4F46E5",
        "accent_text": "#4F46E5",
        "on_accent": "#FFFFFF",
        "disabled": "#A3A9B9",
    },
    "dark": {
        "bg": "#0F1424",
        "surface": "#171D31",
        "text": "#E8EAF2",
        "muted": "#98A0BA",
        "accent": "#5A5DEB",
        "accent_text": "#A5B4FC",
        "on_accent": "#FFFFFF",
        "disabled": "#5C647E",
    },
}

_current = "light"


def current_palette() -> dict[str, str]:
    return PALETTES[_current]


def _build_palette(name: str) -> QPalette:
    colors = PALETTES[name]
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: colors["bg"],
        QPalette.ColorRole.WindowText: colors["text"],
        QPalette.ColorRole.Base: colors["surface"],
        QPalette.ColorRole.AlternateBase: colors["bg"],
        QPalette.ColorRole.ToolTipBase: colors["surface"],
        QPalette.ColorRole.ToolTipText: colors["text"],
        QPalette.ColorRole.Text: colors["text"],
        QPalette.ColorRole.Button: colors["surface"],
        QPalette.ColorRole.ButtonText: colors["text"],
        QPalette.ColorRole.Highlight: colors["accent"],
        QPalette.ColorRole.HighlightedText: colors["on_accent"],
        QPalette.ColorRole.PlaceholderText: colors["muted"],
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled"]))
    return palette


class ThemeManager(QObject):
    """Menerapkan palet dan stylesheet, lalu memberi tahu widget agar menyegarkan ikon."""

    theme_changed = Signal(str)

    def __init__(self, app: QApplication, styles_dir: Path) -> None:
        super().__init__()
        self._app = app
        self._styles_dir = Path(styles_dir)

    def apply(self, name: str) -> bool:
        global _current
        if name not in PALETTES:
            log.warning("Tema %r tidak dikenal, memakai tema terang.", name)
            name = "light"
        qss_path = self._styles_dir / f"{name}.qss"
        try:
            stylesheet = qss_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.error("Gagal membaca berkas tema %s: %s", qss_path, exc)
            return False
        _current = name
        self._app.setPalette(_build_palette(name))
        self._app.setStyleSheet(stylesheet)
        self.theme_changed.emit(name)
        return True
