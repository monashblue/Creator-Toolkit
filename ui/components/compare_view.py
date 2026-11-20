"""Tampilan perbandingan sebelum dan sesudah dengan pembatas yang dapat digeser."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.geometry import clamp_ratio, divider_x, fit_rect, ratio_from_x
from ui.theme import current_palette

KEY_STEP = 0.05


class CompareView(QWidget):
    """Kiri menampilkan Sebelum dan kanan menampilkan Sesudah. Geser pembatas dengan mouse atau tombol panah."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._before: QPixmap | None = None
        self._after: QPixmap | None = None
        self._ratio = 0.5
        self._message = "Pilih gambar dari daftar untuk melihat pratinjau."
        self._note = ""
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Perbandingan sebelum dan sesudah")

    def refresh_icons(self) -> None:
        """Dipanggil MainWindow saat tema berganti agar warna lukisan mengikuti tema."""
        self.update()

    def set_message(self, text: str) -> None:
        self._before = self._after = None
        self._message = text
        self.update()

    def set_images(self, before: QPixmap, after: QPixmap | None, note: str = "") -> None:
        self._before, self._after, self._note = before, after, note
        self.update()

    def ratio(self) -> float:
        return self._ratio

    def _image_rect(self) -> QRect:
        assert self._before is not None
        pad = 8
        x, y, w, h = fit_rect(self._before.width(), self._before.height(), self.width() - 2 * pad, self.height() - 2 * pad)
        return QRect(x + pad, y + pad, w, h)

    def paintEvent(self, event) -> None:  # noqa: N802
        colors = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(colors["surface"]))

        if self._before is None:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20), int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), self._message)
            painter.end()
            return

        target = self._image_rect()
        painter.drawPixmap(target, self._before)
        label_bg = QColor(0, 0, 0, 150)

        def tag(text: str, x: int, align: Qt.AlignmentFlag) -> None:
            box = QRect(x, target.top() + 8, 76, 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(label_bg)
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)

        if self._after is not None:
            split = divider_x(target.left(), target.width(), self._ratio)
            painter.save()
            painter.setClipRect(QRect(split, target.top(), target.right() - split + 1, target.height()))
            painter.drawPixmap(target, self._after)
            painter.restore()
            painter.setPen(QPen(QColor(colors["accent"]), 2))
            painter.drawLine(split, target.top(), split, target.bottom())
            painter.setBrush(QColor(colors["accent"]))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(QPoint(split, target.center().y()), 12, 12)
            tag("Sebelum", target.left() + 8, Qt.AlignmentFlag.AlignLeft)
            tag("Sesudah", target.right() - 84, Qt.AlignmentFlag.AlignRight)
        else:
            tag("Sebelum", target.left() + 8, Qt.AlignmentFlag.AlignLeft)
            painter.setPen(QColor(255, 255, 255))
            painter.setBrush(label_bg)
            note_box = QRect(target.left() + 8, target.bottom() - 32, min(260, target.width() - 16), 24)
            painter.drawRoundedRect(note_box, 6, 6)
            painter.drawText(note_box, int(Qt.AlignmentFlag.AlignCenter), self._note or "Belum diproses")
        painter.end()

    def _move_divider(self, x: float) -> None:
        if self._before is None or self._after is None:
            return
        target = self._image_rect()
        self._ratio = ratio_from_x(x, target.left(), target.width())
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._move_divider(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_divider(event.position().x())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Left:
            self._ratio = clamp_ratio(self._ratio - KEY_STEP)
            self.update()
        elif event.key() == Qt.Key.Key_Right:
            self._ratio = clamp_ratio(self._ratio + KEY_STEP)
            self.update()
        else:
            super().keyPressEvent(event)
