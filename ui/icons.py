"""Membuat QPixmap dan QIcon dari data SVG."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.icon_data import build_svg

_SCALE = 2


def make_pixmap(name: str, color: str, size: int = 24) -> QPixmap:
    """Merender ikon pada resolusi 2x agar tetap tajam, dengan ukuran logis `size`."""
    renderer = QSvgRenderer(QByteArray(build_svg(name, color).encode("utf-8")))
    pixmap = QPixmap(size * _SCALE, size * _SCALE)
    pixmap.setDevicePixelRatio(float(_SCALE))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def make_icon(name: str, off_color: str, on_color: str | None = None, size: int = 20) -> QIcon:
    """Ikon dengan warna berbeda untuk keadaan biasa dan keadaan tercentang."""
    icon = QIcon()
    icon.addPixmap(make_pixmap(name, off_color, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(
        make_pixmap(name, on_color or off_color, size), QIcon.Mode.Normal, QIcon.State.On
    )
    return icon
