"""Halaman QR Code Generator. Seluruh logika pembuatan QR ada di processor.py dan exporter.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.logger import get_logger
from core.worker import TaskRunner
from modules.qr_generator import exporter, payloads, processor
from modules.qr_generator.payloads import FieldSpec
from ui.components.buttons import AppButton
from ui.components.cards import Card
from ui.components.color_picker import ColorPicker
from ui.imaging import pil_to_pixmap

if TYPE_CHECKING:
    from app.application import AppContext

log = get_logger("qr.ui")

PREVIEW_SIZE = 300
PREVIEW_DEBOUNCE_MS = 250
PREVIEW_RENDER_PX = 640  # pratinjau dirender kecil agar cepat dan hemat memori

EC_CHOICES = (
    ("L - Rendah (pulih sekitar 7%)", "L"),
    ("M - Sedang (pulih sekitar 15%)", "M"),
    ("Q - Tinggi (pulih sekitar 25%)", "Q"),
    ("H - Sangat tinggi (pulih sekitar 30%)", "H"),
)
FORMAT_HINTS = {
    "PNG": "Cocok untuk web dan cetak, tanpa kehilangan kualitas.",
    "JPG": "Ukuran kecil, tetapi kompresi dapat sedikit mengurangi ketajaman.",
    "SVG": "Vektor yang dapat diperbesar tanpa pecah.",
    "PDF": "Halaman PDF berisi gambar QR beresolusi 300 dpi.",
}
LOGO_FILTER = "Gambar (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class FieldRow(QWidget):
    """Satu kolom isian beserta label, bantuan, dan pesan kesalahan."""

    changed = Signal()

    def __init__(self, spec: FieldSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if spec.kind != payloads.KIND_BOOL:
            label = QLabel(spec.label + (" *" if spec.required else ""))
            label.setObjectName("FieldLabel")
            layout.addWidget(label)

        self._input = self._create_input(spec)
        self._input.setAccessibleName(spec.label)
        layout.addWidget(self._input)

        if spec.help:
            help_label = QLabel(spec.help)
            help_label.setObjectName("Muted")
            help_label.setWordWrap(True)
            layout.addWidget(help_label)

        self._error = QLabel()
        self._error.setObjectName("FieldError")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

    def _create_input(self, spec: FieldSpec) -> QWidget:
        if spec.kind == payloads.KIND_MULTILINE:
            widget = QPlainTextEdit()
            widget.setPlaceholderText(spec.placeholder)
            widget.setFixedHeight(84)
            widget.textChanged.connect(lambda: self.changed.emit())
        elif spec.kind == payloads.KIND_CHOICE:
            widget = QComboBox()
            for text, value in spec.choices:
                widget.addItem(text, value)
            widget.currentIndexChanged.connect(lambda *_: self.changed.emit())
        elif spec.kind == payloads.KIND_BOOL:
            widget = QCheckBox(spec.label)
            widget.toggled.connect(lambda *_: self.changed.emit())
        else:
            widget = QLineEdit()
            widget.setPlaceholderText(spec.placeholder)
            widget.textChanged.connect(lambda *_: self.changed.emit())
        return widget

    def value(self) -> Any:
        widget = self._input
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QComboBox):
            return widget.currentData()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return widget.text()

    def set_value(self, value: Any) -> None:
        widget = self._input
        widget.blockSignals(True)
        try:
            if isinstance(widget, QPlainTextEdit):
                widget.setPlainText(str(value))
            elif isinstance(widget, QComboBox):
                index = widget.findData(value)
                widget.setCurrentIndex(max(index, 0))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            else:
                widget.setText(str(value))
        finally:
            widget.blockSignals(False)

    def set_error(self, message: str | None) -> None:
        self._input.setProperty("invalid", bool(message))
        _repolish(self._input)
        if message:
            self._error.setText(message)
            self._error.show()
        else:
            self._error.hide()


class QRGeneratorPage(QWidget):
    """Halaman utama QR Code Generator: isian, tampilan, logo, pratinjau langsung, dan ekspor."""

    exported = Signal(str)

    def __init__(self, context: "AppContext", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._rows: dict[str, FieldRow] = {}
        self._values: dict[str, dict[str, Any]] = {}
        self._touched: dict[str, set[str]] = {}
        self._active_type = payloads.QR_TYPES[0].type_id
        self._show_all_errors = False
        self._result: processor.QRResult | None = None
        self._logo_path: str | None = None
        self._last_export_dir: Path | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._timer.timeout.connect(self._update_preview)

        self._dir_touched = False
        self._preview_dirty = False
        self._preview_runner = TaskRunner(self)
        self._preview_runner.succeeded.connect(self._on_preview_ready)
        self._preview_runner.failed.connect(self._on_preview_failed)
        self._preview_runner.finished.connect(self._on_preview_finished)
        self._export_runner = TaskRunner(self)
        self._export_runner.succeeded.connect(self._on_export_ready)
        self._export_runner.failed.connect(self._on_export_failed)
        self._export_runner.finished.connect(self._on_export_finished)

        self._build_ui()
        self._rebuild_fields(self._active_type)
        self._on_ec_changed()
        self._on_format_changed()
        self._schedule_preview()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Membatalkan pekerjaan yang berjalan saat aplikasi ditutup."""
        self._timer.stop()
        self._preview_runner.shutdown()
        self._export_runner.shutdown()

    def showEvent(self, event) -> None:  # noqa: N802
        """Folder bawaan di Pengaturan berlaku lagi bila pengguna belum memilih folder sendiri di halaman ini."""
        super().showEvent(event)
        if not self._dir_touched:
            self._dir_edit.setText(self._default_dir())

    def _default_dir(self) -> str:
        config = self._context.config
        return str(config.get("qr.output_directory") or config.get("output_directory", ""))

    def _mark_dir_touched(self, *_args: object) -> None:
        self._dir_touched = True

    # ------------------------------------------------------------ pembangunan UI

    def _card(self, title: str) -> tuple[Card, QVBoxLayout]:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        return card, layout

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return box

    def _build_ui(self) -> None:
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(14)

        title = QLabel("QR Code Generator")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Buat kode QR statis tanpa server eksternal. Pratinjau diperbarui otomatis saat Anda mengetik."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("PageRoot")
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(14)
        form.addWidget(self._build_type_card())
        form.addWidget(self._build_fields_card())
        form.addWidget(self._build_appearance_card())
        form.addWidget(self._build_logo_card())
        form.addWidget(self._build_export_card())
        form.addStretch(1)
        scroll.setWidget(content)

        preview_column = QWidget()
        preview_column.setFixedWidth(PREVIEW_SIZE + 40)
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self._build_preview_card())
        preview_layout.addStretch(1)

        body.addWidget(scroll, 1)
        body.addWidget(preview_column, 0)
        outer.addLayout(body, 1)

    def _build_type_card(self) -> Card:
        card, layout = self._card("1. Jenis QR")
        self._type_combo = QComboBox()
        self._type_combo.setAccessibleName("Jenis QR")
        for spec in payloads.QR_TYPES:
            self._type_combo.addItem(spec.label, spec.type_id)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._type_description = QLabel()
        self._type_description.setObjectName("CardText")
        self._type_description.setWordWrap(True)
        layout.addWidget(self._type_combo)
        layout.addWidget(self._type_description)
        return card

    def _build_fields_card(self) -> Card:
        card, layout = self._card("2. Isi QR")
        self._fields_layout = QVBoxLayout()
        self._fields_layout.setSpacing(12)
        layout.addLayout(self._fields_layout)
        return card

    def _build_appearance_card(self) -> Card:
        card, layout = self._card("3. Tampilan")
        self._fg_picker = ColorPicker("Warna depan", "#000000")
        self._bg_picker = ColorPicker("Warna latar", "#FFFFFF")
        self._fg_picker.changed.connect(self._schedule_preview)
        self._bg_picker.changed.connect(self._schedule_preview)
        layout.addWidget(self._labeled("Warna depan", self._fg_picker))
        layout.addWidget(self._labeled("Warna latar", self._bg_picker))

        self._size_spin = QSpinBox()
        self._size_spin.setRange(processor.MIN_SIZE, processor.MAX_SIZE)
        self._size_spin.setSingleStep(64)
        self._size_spin.setValue(512)
        self._size_spin.setSuffix(" px")
        self._size_spin.setAccessibleName("Ukuran QR")
        self._size_spin.valueChanged.connect(lambda *_: self._schedule_preview())
        layout.addWidget(self._labeled("Ukuran (piksel)", self._size_spin))

        self._ec_combo = QComboBox()
        self._ec_combo.setAccessibleName("Koreksi kesalahan")
        for text, value in EC_CHOICES:
            self._ec_combo.addItem(text, value)
        self._ec_combo.setCurrentIndex(1)
        self._ec_combo.currentIndexChanged.connect(self._on_ec_changed)
        layout.addWidget(self._labeled("Koreksi kesalahan", self._ec_combo))

        self._border_spin = QSpinBox()
        self._border_spin.setRange(processor.MIN_BORDER, processor.MAX_BORDER)
        self._border_spin.setValue(processor.STANDARD_BORDER)
        self._border_spin.setSuffix(" modul")
        self._border_spin.setAccessibleName("Zona tenang")
        self._border_spin.valueChanged.connect(lambda *_: self._schedule_preview())
        layout.addWidget(self._labeled("Zona tenang (tepi kosong)", self._border_spin))
        return card

    def _build_logo_card(self) -> Card:
        card, layout = self._card("4. Logo di tengah (opsional)")
        row = QHBoxLayout()
        self._logo_button = AppButton("Pilih logo...", "secondary")
        self._logo_button.clicked.connect(self._choose_logo)
        self._logo_remove = AppButton("Hapus logo", "ghost")
        self._logo_remove.setEnabled(False)
        self._logo_remove.clicked.connect(self._remove_logo)
        row.addWidget(self._logo_button)
        row.addWidget(self._logo_remove)
        row.addStretch(1)
        layout.addLayout(row)

        self._logo_label = QLabel("Belum ada logo")
        self._logo_label.setObjectName("CardText")
        self._logo_label.setWordWrap(True)
        layout.addWidget(self._logo_label)

        self._logo_size_label = QLabel()
        self._logo_size_label.setObjectName("FieldLabel")
        self._logo_slider = QSlider(Qt.Orientation.Horizontal)
        self._logo_slider.setRange(5, 25)
        self._logo_slider.setValue(20)
        self._logo_slider.setAccessibleName("Ukuran logo")
        self._logo_slider.valueChanged.connect(self._on_logo_ratio_changed)
        layout.addWidget(self._logo_size_label)
        layout.addWidget(self._logo_slider)

        self._logo_hint = QLabel()
        self._logo_hint.setObjectName("Muted")
        self._logo_hint.setWordWrap(True)
        layout.addWidget(self._logo_hint)
        return card

    def _build_export_card(self) -> Card:
        card, layout = self._card("5. Simpan")
        self._format_combo = QComboBox()
        self._format_combo.setAccessibleName("Format berkas")
        for fmt in exporter.FORMATS:
            self._format_combo.addItem(fmt, fmt)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        self._format_hint = QLabel()
        self._format_hint.setObjectName("Muted")
        self._format_hint.setWordWrap(True)
        layout.addWidget(self._labeled("Format", self._format_combo))
        layout.addWidget(self._format_hint)

        self._dir_edit = QLineEdit(self._default_dir())
        self._dir_edit.setAccessibleName("Folder penyimpanan")
        self._dir_edit.textEdited.connect(self._mark_dir_touched)
        folder_button = AppButton("Pilih folder...", "secondary")
        folder_button.clicked.connect(self._choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._dir_edit, 1)
        folder_row.addWidget(folder_button)
        folder_box = QWidget()
        folder_box.setLayout(folder_row)
        folder_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._labeled("Folder penyimpanan", folder_box))

        self._name_edit = QLineEdit(exporter.DEFAULT_STEM)
        self._name_edit.setAccessibleName("Nama berkas")
        layout.addWidget(self._labeled("Nama berkas (tanpa ekstensi)", self._name_edit))

        self._save_button = AppButton("Simpan QR", "primary")
        self._save_button.clicked.connect(self._save)
        layout.addWidget(self._save_button)

        self._export_status = QLabel()
        self._export_status.setObjectName("CardText")
        self._export_status.setWordWrap(True)
        self._export_status.hide()
        self._export_error = QLabel()
        self._export_error.setObjectName("ErrorText")
        self._export_error.setWordWrap(True)
        self._export_error.hide()
        self._open_folder_button = AppButton("Buka folder hasil", "ghost")
        self._open_folder_button.clicked.connect(self._open_export_folder)
        self._open_folder_button.hide()
        layout.addWidget(self._export_status)
        layout.addWidget(self._export_error)
        layout.addWidget(self._open_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_preview_card(self) -> Card:
        card, layout = self._card("Pratinjau")
        self._preview = QLabel()
        self._preview.setObjectName("PreviewImage")
        self._preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setWordWrap(True)
        self._preview.setAccessibleName("Pratinjau kode QR")
        self._info = QLabel()
        self._info.setObjectName("Muted")
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info.setWordWrap(True)
        self._warning = QLabel()
        self._warning.setObjectName("WarningText")
        self._warning.setWordWrap(True)
        self._warning.hide()
        self._error = QLabel()
        self._error.setObjectName("ErrorText")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._info)
        layout.addWidget(self._warning)
        layout.addWidget(self._error)
        return card

    # ------------------------------------------------------------ isian dinamis

    def _current_type(self) -> str:
        return self._type_combo.currentData() or payloads.QR_TYPES[0].type_id

    def _on_type_changed(self, *_args: object) -> None:
        self._values[self._active_type] = self._collect_values()
        self._rebuild_fields(self._current_type())
        self._schedule_preview()

    def _rebuild_fields(self, type_id: str) -> None:
        for row in self._rows.values():
            self._fields_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = {}
        spec = payloads.get_type_spec(type_id)
        self._active_type = type_id
        self._type_description.setText(spec.description)
        saved = self._values.get(type_id, {})
        for field in spec.fields:
            row = FieldRow(field)
            row.changed.connect(lambda key=field.key: self._on_field_changed(key))
            if field.key in saved:
                row.set_value(saved[field.key])
            self._fields_layout.addWidget(row)
            self._rows[field.key] = row

    def _on_field_changed(self, key: str) -> None:
        self._touched.setdefault(self._active_type, set()).add(key)
        self._schedule_preview()

    def _collect_values(self) -> dict[str, Any]:
        return {key: row.value() for key, row in self._rows.items()}

    def _collect_settings(self) -> processor.QRSettings:
        return processor.QRSettings(
            foreground=self._fg_picker.color(),
            background=self._bg_picker.color(),
            size_px=self._size_spin.value(),
            error_correction=self._ec_combo.currentData() or "M",
            border=self._border_spin.value(),
            logo_path=self._logo_path,
            logo_ratio=self._logo_slider.value() / 100,
        )

    # ------------------------------------------------------------ logo dan pengaturan

    def _on_ec_changed(self, *_args: object) -> None:
        ec = self._ec_combo.currentData() or "M"
        percent = int(processor.max_logo_ratio(ec) * 100)
        if percent > 0:
            self._logo_slider.setRange(5, percent)
            self._logo_slider.setEnabled(True)
            self._logo_hint.setText(
                f"Batas ukuran logo untuk koreksi {ec} adalah {percent}% dari lebar kode agar tetap terbaca."
            )
        else:
            self._logo_slider.setEnabled(False)
            self._logo_hint.setText("Logo tidak dapat dipakai pada koreksi L. Pilih koreksi M atau lebih tinggi.")
        self._on_logo_ratio_changed(self._logo_slider.value())

    def _on_logo_ratio_changed(self, value: int) -> None:
        self._logo_size_label.setText(f"Ukuran logo: {value}%")
        self._schedule_preview()

    def _choose_logo(self) -> None:
        start = str(self._context.config.get("last_used_directory", ""))
        path, _ = QFileDialog.getOpenFileName(self, "Pilih logo", start, LOGO_FILTER)
        if not path:
            return
        self._logo_path = path
        self._logo_label.setText(Path(path).name)
        self._logo_remove.setEnabled(True)
        self._save_config("last_used_directory", str(Path(path).parent))
        self._schedule_preview()

    def _remove_logo(self) -> None:
        self._logo_path = None
        self._logo_label.setText("Belum ada logo")
        self._logo_remove.setEnabled(False)
        self._schedule_preview()

    def _on_format_changed(self, *_args: object) -> None:
        self._format_hint.setText(FORMAT_HINTS.get(self._format_combo.currentData(), ""))

    # ------------------------------------------------------------ pratinjau

    def _schedule_preview(self) -> None:
        self._timer.start()

    def _set_placeholder(self, text: str) -> None:
        self._preview.setPixmap(QPixmap())
        self._preview.setText(text)
        self._info.setText("")
        self._warning.hide()

    def _show_field_errors(self, errors: dict[str, str]) -> None:
        touched = self._touched.get(self._active_type, set())
        for key, row in self._rows.items():
            show = key in errors and (self._show_all_errors or key in touched)
            row.set_error(errors[key] if show else None)

    @staticmethod
    def _build_outcome(type_id, values, settings, render_size):
        """Dijalankan di worker thread. Mengembalikan (jenis, isi) agar error terstruktur tetap utuh."""
        try:
            return ("ok", processor.generate_qr(type_id, values, settings, render_size_px=render_size))
        except processor.QRValidationError as exc:
            return ("invalid", exc)
        except processor.QRError as exc:
            return ("error", str(exc))
        except ImportError:
            log.exception("Pustaka qrcode tidak ditemukan.")
            return ("error", "Pustaka qrcode belum terpasang. Jalankan: pip install -r requirements.txt")

    def _update_preview(self) -> None:
        if self._preview_runner.is_running():
            self._preview_dirty = True  # dijalankan ulang setelah pekerjaan saat ini selesai
            return
        type_id, values, settings = self._current_type(), self._collect_values(), self._collect_settings()
        self._preview_dirty = False
        self._preview_runner.start(lambda ctx: self._build_outcome(type_id, values, settings, PREVIEW_RENDER_PX))

    def _on_preview_ready(self, outcome: object) -> None:
        if self._preview_dirty:
            return  # masukan sudah berubah, hasil ini usang
        kind, payload = outcome  # type: ignore[misc]
        self._error.hide()
        if kind == "invalid":
            self._result = None
            self._show_field_errors(payload.field_errors)
            self._set_placeholder("Lengkapi isian di sebelah kiri untuk melihat pratinjau.")
            if payload.setting_errors:
                self._error.setText("\n".join(payload.setting_errors.values()))
                self._error.show()
            return
        if kind == "error":
            self._result = None
            self._show_field_errors({})
            self._set_placeholder("Kode QR tidak dapat dibuat.")
            self._error.setText(payload)
            self._error.show()
            return

        result = payload
        self._result = result
        self._show_field_errors({})
        pixmap = pil_to_pixmap(result.image)
        mode = (
            Qt.TransformationMode.FastTransformation
            if pixmap.width() < PREVIEW_SIZE
            else Qt.TransformationMode.SmoothTransformation
        )
        self._preview.setText("")
        self._preview.setPixmap(
            pixmap.scaled(PREVIEW_SIZE - 2, PREVIEW_SIZE - 2, Qt.AspectRatioMode.KeepAspectRatio, mode)
        )
        self._info.setText(
            f"Hasil {result.final_size_px} x {result.final_size_px} px  |  versi {result.version}  |  {result.modules} modul"
        )
        if result.warnings:
            self._warning.setText("\n".join("\u2022 " + warning for warning in result.warnings))
            self._warning.show()
        else:
            self._warning.hide()

    def _on_preview_failed(self, message: str) -> None:
        self._result = None
        self._set_placeholder("Kode QR tidak dapat dibuat.")
        self._error.setText(message)
        self._error.show()

    def _on_preview_finished(self) -> None:
        if self._preview_dirty:
            self._update_preview()

    # ------------------------------------------------------------ simpan

    def _save_config(self, key: str, value: str) -> None:
        try:
            self._context.config.set(key, value)
        except OSError:
            log.exception("Gagal menyimpan pengaturan %s", key)

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Pilih folder penyimpanan", self._dir_edit.text())
        if chosen:
            self._dir_touched = True
            self._dir_edit.setText(chosen)

    @staticmethod
    def _export_outcome(type_id, values, settings, directory, name, fmt):
        """Dijalankan di worker thread: membuat QR ukuran penuh lalu menyimpannya."""
        try:
            result = processor.generate_qr(type_id, values, settings)
            return ("ok", exporter.export_qr(result, directory, name, fmt))
        except processor.QRValidationError as exc:
            return ("invalid", exc)
        except exporter.ExportError as exc:
            return ("export_error", str(exc))
        except processor.QRError as exc:
            return ("error", str(exc))
        except ImportError:
            log.exception("Pustaka qrcode tidak ditemukan.")
            return ("error", "Pustaka qrcode belum terpasang. Jalankan: pip install -r requirements.txt")

    def _save(self) -> None:
        if self._export_runner.is_running():
            return
        self._export_status.hide()
        self._export_error.hide()
        self._open_folder_button.hide()

        folder = self._dir_edit.text().strip()
        if not folder:
            self._export_error.setText("Pilih folder penyimpanan terlebih dahulu.")
            self._export_error.show()
            return

        self._show_all_errors = True
        type_id, values, settings = self._current_type(), self._collect_values(), self._collect_settings()
        directory = Path(folder).expanduser()
        name, fmt = self._name_edit.text(), self._format_combo.currentData()
        self._save_button.setEnabled(False)
        self._export_status.setText("Menyimpan...")
        self._export_status.show()
        self._export_runner.start(
            lambda ctx: self._export_outcome(type_id, values, settings, directory, name, fmt)
        )

    def _on_export_ready(self, outcome: object) -> None:
        kind, payload = outcome  # type: ignore[misc]
        self._export_status.hide()
        if kind == "invalid":
            self._show_field_errors(payload.field_errors)
            self._export_error.setText("Perbaiki isian yang ditandai merah sebelum menyimpan.")
            self._export_error.show()
            return
        if kind in ("error", "export_error"):
            self._export_error.setText(payload)
            self._export_error.show()
            if kind == "export_error":
                QMessageBox.warning(self, "Simpan QR", payload)
            return

        saved = payload
        self._last_export_dir = saved.path.parent
        self._save_config("qr.output_directory", self._dir_edit.text().strip())
        lines = [f"Tersimpan: {saved.path}"] + ["\u2022 " + warning for warning in saved.warnings]
        self._export_status.setText("\n".join(lines))
        self._export_status.show()
        self._open_folder_button.show()
        log.info("QR %s disimpan ke %s", self._current_type(), saved.path)
        self.exported.emit(str(saved.path))

    def _on_export_failed(self, message: str) -> None:
        self._export_status.hide()
        self._export_error.setText(message)
        self._export_error.show()
        QMessageBox.warning(self, "Simpan QR", message)

    def _on_export_finished(self) -> None:
        self._save_button.setEnabled(True)

    def _open_export_folder(self) -> None:
        if self._last_export_dir is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_export_dir))):
            QMessageBox.warning(self, "Simpan QR", f"Folder tidak dapat dibuka: {self._last_export_dir}")
