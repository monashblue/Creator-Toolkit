"""Panel progres: pesan, batang progres, dan tombol batal."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from ui.components.buttons import AppButton


class ProgressPanel(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._label = QLabel()
        self._label.setObjectName("CardText")
        self._label.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(True)
        self._cancel = AppButton("Batalkan", "secondary")
        self._cancel.clicked.connect(self.cancel_requested.emit)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        layout.addWidget(self._cancel, 0, Qt.AlignmentFlag.AlignLeft)
        self.reset()

    def start(self, message: str = "") -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._label.setText(message)
        self._cancel.setEnabled(True)
        self._cancel.setText("Batalkan")
        self.show()

    def set_progress(self, percent: int, message: str = "") -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(percent)
        if message:
            self._label.setText(message)

    def set_cancelling(self) -> None:
        self._cancel.setEnabled(False)
        self._cancel.setText("Membatalkan...")
        self._label.setText("Membatalkan setelah langkah yang sedang berjalan selesai...")

    def reset(self) -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._label.setText("")
        self.hide()
