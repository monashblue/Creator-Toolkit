"""Area seret dan lepas berkas, sekaligus tombol untuk memilih berkas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class DropZone(QFrame):
    """Memancarkan files_dropped (daftar jalur) saat berkas dilepas dan browse_requested saat diklik."""

    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, title: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(96)
        self.setAccessibleName(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label = QLabel(hint)
        hint_label.setObjectName("Muted")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        for label in (title_label, hint_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)

    def _set_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browse_requested.emit()
            return
        super().keyPressEvent(event)
