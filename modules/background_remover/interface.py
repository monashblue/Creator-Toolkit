"""Halaman Background Remover. Pemrosesan dan unduhan berjalan di worker thread."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.file_manager import InvalidImageError, expand_paths, inspect_image
from core.logger import get_logger
from core.worker import TaskRunner
from modules.background_remover import processor
from modules.background_remover.errors import ModelInvalidError
from modules.background_remover.model_manager import (
    DEFAULT_MODEL_ID,
    ModelManager,
    ModelSpec,
    ModelStatus,
    format_size,
)
from ui.components.buttons import AppButton
from ui.components.cards import Card
from ui.components.color_picker import ColorPicker
from ui.components.compare_view import CompareView
from ui.components.dropzone import DropZone
from ui.components.progress import ProgressPanel
from ui.imaging import pil_to_pixmap

if TYPE_CHECKING:
    from app.application import AppContext

log = get_logger("bg.ui")

PREVIEW_CACHE_SIZE = 8
IMAGE_FILTER = "Gambar (*.jpg *.jpeg *.png *.webp)"

STATUS_WAITING = "Menunggu"
STATUS_DONE = "Selesai"
STATUS_FAILED = "Gagal"
STATUS_CANCELLED = "Dibatalkan"


@dataclass
class ItemState:
    path: Path
    status: str = STATUS_WAITING
    output: Path | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    def label(self) -> str:
        text = f"{self.path.name}    [{self.status}]"
        if self.status == STATUS_FAILED and self.message:
            text += f" {self.message}"
        return text


class BackgroundRemoverPage(QWidget):
    """Hapus latar belakang gambar dengan model AI lokal, dengan pratinjau sebelum dan sesudah."""

    processed = Signal(list)  # daftar dict {input, output, status} untuk dicatat ke riwayat

    def __init__(self, context: "AppContext", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._context = context
        self._manager = ModelManager(context.paths.models_dir)
        self._items: list[ItemState] = []
        self._background_image: str | None = None
        self._last_output_dir: Path | None = None
        self._preview_cache: "OrderedDict[tuple[str, int], QPixmap]" = OrderedDict()
        self._busy: str | None = None

        self._process_runner = TaskRunner(self)
        self._process_runner.progress.connect(self._on_process_progress)
        self._process_runner.item_done.connect(self._on_item_done)
        self._process_runner.succeeded.connect(self._on_process_succeeded)
        self._process_runner.failed.connect(self._on_process_failed)
        self._process_runner.cancelled.connect(self._on_process_cancelled)
        self._process_runner.finished.connect(self._on_process_finished)

        self._download_runner = TaskRunner(self)
        self._download_runner.progress.connect(self._on_download_progress)
        self._download_runner.succeeded.connect(self._on_download_succeeded)
        self._download_runner.failed.connect(self._on_download_failed)
        self._download_runner.cancelled.connect(self._on_download_cancelled)
        self._download_runner.finished.connect(self._on_download_finished)

        self._dir_touched = False
        self._preview_errors: dict[tuple[str, int], str] = {}
        self._preview_inflight: list[tuple[str, int]] = []
        self._preview_runner = TaskRunner(self)
        self._preview_runner.succeeded.connect(self._on_preview_loaded)
        self._preview_runner.failed.connect(self._on_preview_failed)
        self._preview_runner.finished.connect(self._on_preview_finished)

        self._build_ui()
        self._refresh_model()
        self._update_controls()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Membatalkan pekerjaan yang berjalan saat aplikasi ditutup."""
        self._process_runner.shutdown()
        self._download_runner.shutdown()
        self._preview_runner.shutdown()

    def showEvent(self, event) -> None:  # noqa: N802
        """Folder bawaan di Pengaturan berlaku lagi bila pengguna belum memilih folder sendiri di halaman ini."""
        super().showEvent(event)
        if not self._dir_touched:
            self._dir_edit.setText(self._default_dir())

    def _default_dir(self) -> str:
        config = self._context.config
        return str(config.get("background_remover.output_directory") or config.get("output_directory", ""))

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
    def _label(text: str, name: str = "CardText") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _build_ui(self) -> None:
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(14)
        title = QLabel("Background Remover")
        title.setObjectName("PageTitle")
        outer.addWidget(title)
        outer.addWidget(
            self._label(
                "Hapus latar belakang gambar dengan model AI yang berjalan di komputer Anda. "
                "Gambar tidak pernah dikirim ke internet dan gambar asli tidak diubah.",
                "PageSubtitle",
            )
        )

        body = QHBoxLayout()
        body.setSpacing(20)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(330)
        content = QWidget()
        content.setObjectName("PageRoot")
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(14)
        for card in (
            self._build_model_card(),
            self._build_files_card(),
            self._build_background_card(),
            self._build_output_card(),
            self._build_process_card(),
        ):
            form.addWidget(card)
        form.addStretch(1)
        scroll.setWidget(content)

        body.addWidget(scroll, 5)
        body.addWidget(self._build_preview_card(), 6)
        outer.addLayout(body, 1)

    def _build_model_card(self) -> Card:
        card, layout = self._card("1. Model AI")
        self._model_combo = QComboBox()
        self._model_combo.setAccessibleName("Model AI")
        for spec in self._manager.catalog:
            self._model_combo.addItem(spec.display_name, spec.model_id)
        saved = self._context.config.get("background_remover.model") or DEFAULT_MODEL_ID
        self._model_combo.setCurrentIndex(max(self._model_combo.findData(saved), 0))
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        self._model_info = self._label("")
        self._model_status = self._label("", "FieldLabel")
        self._model_error = self._label("", "ErrorText")
        self._model_error.hide()
        self._download_button = AppButton("Unduh model...", "primary")
        self._download_button.clicked.connect(self._on_download_clicked)
        self._download_panel = ProgressPanel()
        self._download_panel.cancel_requested.connect(self._cancel_download)
        layout.addWidget(self._model_combo)
        layout.addWidget(self._model_info)
        layout.addWidget(self._model_status)
        layout.addWidget(self._download_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._download_panel)
        layout.addWidget(self._model_error)
        return card

    def _build_files_card(self) -> Card:
        card, layout = self._card("2. Gambar")
        self._dropzone = DropZone(
            "Seret gambar atau folder ke sini", "atau klik untuk memilih berkas. Format: JPG, PNG, WEBP."
        )
        self._dropzone.files_dropped.connect(self._add_paths)
        self._dropzone.browse_requested.connect(self._browse_files)
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setMinimumHeight(130)
        self._list.setAccessibleName("Daftar gambar")
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._files_note = self._label("", "WarningText")
        self._files_note.hide()
        row = QHBoxLayout()
        self._add_button = AppButton("Tambah gambar...", "secondary")
        self._add_button.clicked.connect(self._browse_files)
        self._remove_button = AppButton("Hapus terpilih", "ghost")
        self._remove_button.clicked.connect(self._remove_selected)
        self._clear_button = AppButton("Kosongkan", "ghost")
        self._clear_button.clicked.connect(self._clear_items)
        row.addWidget(self._add_button)
        row.addWidget(self._remove_button)
        row.addWidget(self._clear_button)
        row.addStretch(1)
        layout.addWidget(self._dropzone)
        layout.addWidget(self._list)
        layout.addLayout(row)
        layout.addWidget(self._files_note)
        return card

    def _build_background_card(self) -> Card:
        card, layout = self._card("3. Latar belakang hasil")
        self._radio_transparent = QRadioButton("Transparan (PNG dengan kanal alpha)")
        self._radio_color = QRadioButton("Warna solid")
        self._radio_image = QRadioButton("Gambar lain")
        self._radio_transparent.setChecked(True)
        group = QButtonGroup(self)
        for radio in (self._radio_transparent, self._radio_color, self._radio_image):
            group.addButton(radio)
            radio.toggled.connect(self._update_controls)
        self._color_picker = ColorPicker("Warna latar", "#FFFFFF")
        self._image_button = AppButton("Pilih gambar latar...", "secondary")
        self._image_button.clicked.connect(self._choose_background_image)
        self._image_label = self._label("Belum ada gambar latar")
        layout.addWidget(self._radio_transparent)
        layout.addWidget(self._radio_color)
        layout.addWidget(self._color_picker)
        layout.addWidget(self._radio_image)
        layout.addWidget(self._image_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._image_label)
        layout.addWidget(self._label("Perubahan latar berlaku saat Anda memproses gambar lagi.", "Muted"))
        return card

    def _build_output_card(self) -> Card:
        card, layout = self._card("4. Folder hasil")
        self._dir_edit = QLineEdit(self._default_dir())
        self._dir_edit.setAccessibleName("Folder hasil")
        self._dir_edit.textEdited.connect(self._mark_dir_touched)
        browse = AppButton("Pilih folder...", "secondary")
        browse.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.addWidget(self._dir_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(
            self._label("Hasil disimpan sebagai PNG berakhiran -tanpa-latar. Berkas yang sudah ada tidak pernah ditimpa.", "Muted")
        )
        return card

    def _build_process_card(self) -> Card:
        card, layout = self._card("5. Proses")
        self._process_button = AppButton("Hapus Latar Belakang", "primary")
        self._process_button.clicked.connect(self._start_processing)
        self._process_hint = self._label("", "Muted")
        self._process_panel = ProgressPanel()
        self._process_panel.cancel_requested.connect(self._cancel_processing)
        self._summary = self._label("")
        self._summary.hide()
        self._process_error = self._label("", "ErrorText")
        self._process_error.hide()
        self._open_button = AppButton("Buka folder hasil", "ghost")
        self._open_button.clicked.connect(self._open_output_folder)
        self._open_button.hide()
        layout.addWidget(self._process_button)
        layout.addWidget(self._process_hint)
        layout.addWidget(self._process_panel)
        layout.addWidget(self._summary)
        layout.addWidget(self._process_error)
        layout.addWidget(self._open_button, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_preview_card(self) -> Card:
        card, layout = self._card("Pratinjau sebelum dan sesudah")
        self._compare = CompareView()
        self._checker_toggle = QCheckBox("Tampilkan kotak-kotak untuk area transparan")
        self._checker_toggle.setChecked(True)
        self._checker_toggle.toggled.connect(self._refresh_preview)
        self._preview_info = self._label("", "Muted")
        layout.addWidget(self._compare, 1)
        layout.addWidget(self._label("Geser pembatas dengan mouse atau tombol panah kiri dan kanan.", "Muted"))
        layout.addWidget(self._checker_toggle)
        layout.addWidget(self._preview_info)
        return card

    # ------------------------------------------------------------ model

    def _current_spec(self) -> ModelSpec:
        return self._manager.get(self._model_combo.currentData() or DEFAULT_MODEL_ID)

    def _model_ready(self) -> bool:
        return self._manager.status(self._current_spec()) == ModelStatus.PRESENT

    def _refresh_model(self) -> None:
        spec = self._current_spec()
        status = self._manager.status(spec)
        size = f"sekitar {spec.approx_size_mb} MB" if spec.approx_size_mb else "ukuran tidak diketahui"
        extra = f" {spec.license_note}." if spec.license_note else ""
        self._model_info.setText(f"{spec.description} Ukuran unduhan {size}.{extra}")
        if status == ModelStatus.PRESENT:
            self._model_status.setText("Status: siap digunakan, tanpa internet.")
            self._download_button.hide()
        elif status == ModelStatus.PARTIAL:
            partial = format_size(self._manager.partial_bytes(spec))
            self._model_status.setText(f"Status: unduhan sebagian ({partial}). Dapat dilanjutkan.")
            self._download_button.setText("Lanjutkan unduhan...")
            self._download_button.show()
        else:
            self._model_status.setText("Status: belum diunduh. Model perlu diunduh sekali dengan persetujuan Anda.")
            self._download_button.setText("Unduh model...")
            self._download_button.show()
        self._update_controls()

    def _on_model_changed(self, *_args: object) -> None:
        self._model_error.hide()
        try:
            self._context.config.set("background_remover.model", self._current_spec().model_id)
        except OSError:
            log.exception("Gagal menyimpan pilihan model.")
        self._refresh_model()

    def _confirm_download(self, spec: ModelSpec) -> bool:
        size = f"sekitar {spec.approx_size_mb} MB" if spec.approx_size_mb else "ukuran tidak diketahui"
        partial = self._manager.partial_bytes(spec)
        resume = f"\nUnduhan sebelumnya ({format_size(partial)}) akan dilanjutkan.\n" if partial else ""
        integrity = (
            "Integritas diperiksa dengan checksum."
            if spec.checksum
            else "Integritas diperiksa dari kelengkapan ukuran berkas dan keberhasilan memuat model. "
            "Checksum resmi belum tersedia di katalog."
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Unduh model AI")
        box.setText(
            f"Fitur ini memerlukan model AI \"{spec.display_name}\".\n\n"
            f"Ukuran unduhan: {size}\n"
            f"Sumber: {spec.source_host}\n"
            f"Disimpan di: {self._manager.models_dir}\n"
            f"{resume}\n"
            "Model hanya diunduh sekali. Setelah itu fitur berjalan sepenuhnya tanpa internet, "
            "dan tidak ada gambar Anda yang dikirim ke mana pun.\n\n"
            f"{integrity}\n\nUnduh sekarang?"
        )
        box.addButton("Unduh", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Batal", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        return clicked is not None and box.buttonRole(clicked) == QMessageBox.ButtonRole.AcceptRole

    def _on_download_clicked(self) -> None:
        if self._busy:
            return
        spec = self._current_spec()
        if not self._confirm_download(spec):
            return
        self._model_error.hide()
        manager = self._manager

        def task(ctx):
            state = {"percent": 0}

            def on_progress(done: int, total: int | None) -> None:
                if total:
                    state["percent"] = done * 100 / total
                    ctx.report(state["percent"], f"Mengunduh model: {format_size(done)} dari {format_size(total)}")
                else:
                    ctx.report(0, f"Mengunduh model: {format_size(done)}")

            manager.download(
                spec,
                consent=True,  # pengguna sudah menyetujui lewat dialog di atas
                progress=on_progress,
                status=lambda message: ctx.report(state["percent"], message),
                token=ctx.token,
            )
            ctx.report(99, "Memeriksa dan memuat model...")
            try:
                processor.get_session(spec, manager.path_for(spec))
            except ModelInvalidError:
                manager.remove(spec)  # berkas yang baru diunduh ternyata tidak valid
                raise
            return spec.model_id

        self._busy = "download"
        self._download_panel.start("Menghubungi server...")
        self._update_controls()
        self._download_runner.start(task)

    def _cancel_download(self) -> None:
        self._download_panel.set_cancelling()
        self._download_runner.cancel()

    def _on_download_progress(self, percent: int, message: str) -> None:
        self._download_panel.set_progress(percent, message)

    def _on_download_succeeded(self, _model_id: object) -> None:
        self._model_status.setText("Status: model berhasil diunduh dan siap digunakan tanpa internet.")

    def _on_download_failed(self, message: str) -> None:
        self._model_error.setText(message)
        self._model_error.show()
        QMessageBox.warning(self, "Unduh model AI", message)

    def _on_download_cancelled(self) -> None:
        self._model_error.setText("Unduhan dibatalkan. Anda dapat melanjutkannya kapan saja.")
        self._model_error.show()

    def _on_download_finished(self) -> None:
        self._busy = None
        self._download_panel.reset()
        self._refresh_model()

    # ------------------------------------------------------------ daftar gambar

    def _browse_files(self) -> None:
        start = str(self._context.config.get("last_used_directory", ""))
        paths, _ = QFileDialog.getOpenFileNames(self, "Pilih gambar", start, IMAGE_FILTER)
        if paths:
            try:
                self._context.config.set("last_used_directory", str(Path(paths[0]).parent))
            except OSError:
                log.exception("Gagal menyimpan folder terakhir.")
            self._add_paths(paths)

    def _add_paths(self, paths: list) -> None:
        if self._busy == "process":
            return
        known = {str(item.path) for item in self._items}
        skipped: list[tuple[str, str]] = []
        added = 0
        for path in expand_paths(paths, processor.SUPPORTED_EXTENSIONS):
            if str(path) in known:
                continue
            try:
                inspect_image(path, processor.SUPPORTED_EXTENSIONS, processor.SUPPORTED_FORMATS, processor.MAX_PIXELS)
            except InvalidImageError as exc:
                skipped.append((path.name, str(exc)))
                continue
            item = ItemState(path)
            self._items.append(item)
            self._list.addItem(self._make_list_item(item))
            known.add(str(path))
            added += 1
        if skipped:
            shown = "; ".join(f"{name} ({reason})" for name, reason in skipped[:3])
            more = f" dan {len(skipped) - 3} lainnya" if len(skipped) > 3 else ""
            self._files_note.setText(f"{len(skipped)} berkas dilewati: {shown}{more}.")
            self._files_note.show()
        else:
            self._files_note.hide()
        if added and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)
        self._update_controls()

    @staticmethod
    def _make_list_item(item: ItemState) -> QListWidgetItem:
        entry = QListWidgetItem(item.label())
        entry.setToolTip(str(item.path))
        return entry

    def _refresh_list_item(self, index: int) -> None:
        entry = self._list.item(index)
        if entry is not None:
            entry.setText(self._items[index].label())

    def _remove_selected(self) -> None:
        if self._busy == "process":
            return
        rows = sorted({index.row() for index in self._list.selectedIndexes()}, reverse=True)
        for row in rows:
            self._list.takeItem(row)
            del self._items[row]
        self._after_list_change()

    def _clear_items(self) -> None:
        if self._busy == "process":
            return
        self._list.clear()
        self._items.clear()
        self._after_list_change()

    def _after_list_change(self) -> None:
        self._files_note.hide()
        if self._items and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)
        self._refresh_preview()
        self._update_controls()

    # ------------------------------------------------------------ pengaturan

    def _choose_background_image(self) -> None:
        start = str(self._context.config.get("last_used_directory", ""))
        path, _ = QFileDialog.getOpenFileName(self, "Pilih gambar latar", start, IMAGE_FILTER)
        if not path:
            return
        try:
            inspect_image(Path(path), processor.SUPPORTED_EXTENSIONS, processor.SUPPORTED_FORMATS, processor.MAX_PIXELS)
        except InvalidImageError as exc:
            QMessageBox.warning(self, "Gambar latar", str(exc))
            return
        self._background_image = path
        self._image_label.setText(Path(path).name)
        self._update_controls()

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Pilih folder hasil", self._dir_edit.text())
        if chosen:
            self._dir_touched = True
            self._dir_edit.setText(chosen)

    def _background_options(self) -> processor.BackgroundOptions:
        if self._radio_color.isChecked():
            return processor.BackgroundOptions("color", self._color_picker.color())
        if self._radio_image.isChecked():
            return processor.BackgroundOptions("image", image_path=self._background_image)
        return processor.BackgroundOptions("transparent")

    def _update_controls(self, *_args: object) -> None:
        busy = self._busy is not None
        processing = self._busy == "process"
        self._color_picker.set_picker_enabled(self._radio_color.isChecked() and not processing)
        self._image_button.setEnabled(self._radio_image.isChecked() and not processing)
        self._model_combo.setEnabled(not busy)
        self._download_button.setEnabled(not busy)
        for button in (self._add_button, self._remove_button, self._clear_button):
            button.setEnabled(not processing)
        for radio in (self._radio_transparent, self._radio_color, self._radio_image):
            radio.setEnabled(not processing)
        self._dropzone.setEnabled(not processing)
        ready = self._model_ready()
        can_run = ready and bool(self._items) and not busy
        self._process_button.setEnabled(can_run)
        if busy:
            hint = ""
        elif not ready:
            hint = "Unduh model AI terlebih dahulu."
        elif not self._items:
            hint = "Tambahkan minimal satu gambar."
        else:
            hint = f"{len(self._items)} gambar siap diproses."
        self._process_hint.setText(hint)

    # ------------------------------------------------------------ pemrosesan

    def _validation_problem(self) -> str | None:
        if not self._items:
            return "Tambahkan minimal satu gambar."
        if not self._model_ready():
            return "Unduh model AI terlebih dahulu."
        if not self._dir_edit.text().strip():
            return "Pilih folder hasil terlebih dahulu."
        options = self._background_options()
        if options.mode == "image" and not options.image_path:
            return "Pilih gambar latar belakang, atau ganti ke Transparan atau Warna solid."
        return None

    def _start_processing(self) -> None:
        if self._busy:
            return
        self._process_error.hide()
        self._summary.hide()
        self._open_button.hide()
        problem = self._validation_problem()
        if problem:
            self._process_error.setText(problem)
            self._process_error.show()
            return

        spec = self._current_spec()
        options = self._background_options()
        output_dir = Path(self._dir_edit.text().strip()).expanduser()
        files = [item.path for item in self._items]
        manager = self._manager
        for index, item in enumerate(self._items):
            item.status, item.output, item.message, item.warnings = STATUS_WAITING, None, "", []
            self._refresh_list_item(index)
        self._preview_cache.clear()
        self._preview_errors.clear()
        self._refresh_preview()

        self._last_output_dir = output_dir
        self._busy = "process"
        self._process_panel.start("Menyiapkan...")
        self._update_controls()
        self._process_runner.start(
            lambda ctx: processor.run_background_removal(ctx, manager, spec, files, output_dir, options)
        )

    def _cancel_processing(self) -> None:
        self._process_panel.set_cancelling()
        self._process_runner.cancel()

    def _on_process_progress(self, percent: int, message: str) -> None:
        self._process_panel.set_progress(percent, message)

    def _item_index(self, path: Path) -> int:
        for index, item in enumerate(self._items):
            if item.path == path:
                return index
        return -1

    def _on_item_done(self, result: object) -> None:
        index = self._item_index(result.source)  # type: ignore[attr-defined]
        if index < 0:
            return
        item = self._items[index]
        item.output = result.output  # type: ignore[attr-defined]
        item.message = result.message  # type: ignore[attr-defined]
        item.warnings = list(result.warnings)  # type: ignore[attr-defined]
        item.status = STATUS_DONE if result.status == processor.STATUS_OK else STATUS_FAILED  # type: ignore[attr-defined]
        self._refresh_list_item(index)
        if index == self._list.currentRow():
            self._refresh_preview()

    def _summarize(self, prefix: str) -> None:
        done = sum(1 for item in self._items if item.status == STATUS_DONE)
        failed = sum(1 for item in self._items if item.status == STATUS_FAILED)
        waiting = sum(1 for item in self._items if item.status in (STATUS_WAITING, STATUS_CANCELLED))
        parts = [f"{done} berhasil"]
        if failed:
            parts.append(f"{failed} gagal")
        if waiting:
            parts.append(f"{waiting} belum diproses")
        self._summary.setText(f"{prefix}{', '.join(parts)}.")
        self._summary.show()
        if done and self._last_output_dir is not None:
            self._open_button.show()

    def _history_entries(self) -> list[dict]:
        """Hasil proses terakhir untuk riwayat: berhasil dengan keluarannya, atau gagal tanpa keluaran."""
        entries: list[dict] = []
        for item in self._items:
            if item.status == STATUS_DONE and item.output is not None:
                entries.append({"input": str(item.path), "output": str(item.output), "status": "berhasil"})
            elif item.status == STATUS_FAILED:
                entries.append({"input": str(item.path), "output": None, "status": "gagal"})
        return entries

    def _on_process_succeeded(self, _results: object) -> None:
        self._summarize("Selesai: ")
        entries = self._history_entries()
        if self._last_output_dir is not None:
            try:
                self._context.config.set("background_remover.output_directory", str(self._last_output_dir))
            except OSError:
                log.exception("Gagal menyimpan folder hasil.")
        if entries:
            self.processed.emit(entries)

    def _on_process_failed(self, message: str) -> None:
        self._process_error.setText(message)
        self._process_error.show()
        QMessageBox.warning(self, "Background Remover", message)

    def _on_process_cancelled(self) -> None:
        for index, item in enumerate(self._items):
            if item.status == STATUS_WAITING:
                item.status = STATUS_CANCELLED
                self._refresh_list_item(index)
        self._summarize("Dibatalkan: ")
        entries = self._history_entries()
        if entries:
            self.processed.emit(entries)

    def _on_process_finished(self) -> None:
        self._busy = None
        self._process_panel.reset()
        self._update_controls()
        self._refresh_preview()

    def _open_output_folder(self) -> None:
        if self._last_output_dir is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output_dir))):
            QMessageBox.warning(self, "Background Remover", f"Folder tidak dapat dibuka: {self._last_output_dir}")

    # ------------------------------------------------------------ pratinjau

    def _on_row_changed(self, _row: int) -> None:
        self._refresh_preview()

    @staticmethod
    def _preview_key(path: Path, checkerboard: bool) -> tuple[str, int]:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return f"{path}|{checkerboard}", mtime

    def _cache_pixmap(self, key: tuple[str, int], pixmap: QPixmap) -> None:
        self._preview_cache[key] = pixmap
        self._preview_cache.move_to_end(key)
        while len(self._preview_cache) > PREVIEW_CACHE_SIZE:
            self._preview_cache.popitem(last=False)

    def _refresh_preview(self, *_args: object) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._items):
            self._compare.set_message("Pilih gambar dari daftar untuk melihat pratinjau.")
            self._preview_info.setText("")
            return
        item = self._items[row]
        checker = self._checker_toggle.isChecked()
        wanted: list[tuple[tuple[str, int], Path, bool]] = [(self._preview_key(item.path, False), item.path, False)]
        if item.output is not None and item.output.exists():
            wanted.append((self._preview_key(item.output, checker), item.output, checker))
        missing = [w for w in wanted if w[0] not in self._preview_cache and w[0] not in self._preview_errors]
        if not missing:
            self._show_preview(item, wanted)
            return
        self._compare.set_message("Memuat pratinjau...")
        self._preview_info.setText("")
        if self._preview_runner.is_running():
            return  # _on_preview_finished akan memanggil _refresh_preview lagi
        self._preview_inflight = [w[0] for w in missing]
        self._preview_runner.start(lambda ctx: self._load_previews(missing))

    @staticmethod
    def _load_previews(missing):
        """Dijalankan di worker thread: membaca dan memperkecil gambar. Objek Qt dibuat di thread utama."""
        loaded: dict[tuple[str, int], object] = {}
        errors: dict[tuple[str, int], str] = {}
        for key, path, checker in missing:
            try:
                image = processor.load_preview(path)
                loaded[key] = processor.composite_on_checkerboard(image) if checker else image
            except processor.BackgroundRemoverError as exc:
                errors[key] = str(exc)
        return loaded, errors

    def _on_preview_loaded(self, result: object) -> None:
        loaded, errors = result  # type: ignore[misc]
        for key, image in loaded.items():
            self._cache_pixmap(key, pil_to_pixmap(image))
        self._preview_errors.update(errors)

    def _on_preview_failed(self, message: str) -> None:
        for key in self._preview_inflight:  # tandai gagal agar tidak dicoba terus-menerus
            self._preview_errors[key] = message
        self._compare.set_message(message)

    def _on_preview_finished(self) -> None:
        self._refresh_preview()

    def _show_preview(self, item: ItemState, wanted) -> None:
        before_key = wanted[0][0]
        before = self._preview_cache.get(before_key)
        if before is None:
            self._compare.set_message(self._preview_errors.get(before_key, "Pratinjau tidak tersedia."))
            self._preview_info.setText("")
            return
        after: QPixmap | None = None
        note = "Belum diproses"
        if item.status == STATUS_FAILED:
            note = "Gagal diproses"
        elif item.status == STATUS_CANCELLED:
            note = "Dibatalkan"
        if len(wanted) > 1:
            after = self._preview_cache.get(wanted[1][0])
            if after is None:
                note = "Hasil tidak dapat ditampilkan"
        self._compare.set_images(before, after, note)
        info = [item.path.name]
        if item.status == STATUS_FAILED and item.message:
            info.append(item.message)
        info.extend(item.warnings)
        self._preview_info.setText("\n".join(info))
