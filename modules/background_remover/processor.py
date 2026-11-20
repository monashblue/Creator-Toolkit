"""Mesin penghapus latar belakang: sesi ONNX Runtime CPU, pembacaan gambar, latar pengganti, dan batch.

Tidak bergantung pada Qt dan tidak pernah mengakses jaringan.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from core.file_manager import (
    discard_file,
    inspect_image,
    reserve_unique_path,
    sanitize_filename,
)
from core.logger import get_logger
from core.tasks import OperationCancelled, TaskContext, UserMessageError
from modules.background_remover.errors import (
    BackgroundRemoverError,
    InsufficientMemoryError,
    ModelInvalidError,
    ModelNotAvailableError,
    ProcessingError,
    UnsupportedImageError,
)
from modules.background_remover.model_manager import ModelManager, ModelSpec, ModelStatus

log = get_logger("bg.processor")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 50_000_000
OUTPUT_SUFFIX = "-tanpa-latar"
MODES = ("transparent", "color", "image")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

STATUS_OK = "ok"
STATUS_FAILED = "failed"


# ---------------------------------------------------------------- sesi model

def _is_memory_problem(exc: BaseException) -> bool:
    text = str(exc).lower()
    return isinstance(exc, MemoryError) or "bad_alloc" in text or "failed to allocate" in text or "out of memory" in text


class SegmentationSession:
    """Membungkus InferenceSession ONNX Runtime CPU untuk model segmentasi keluarga U\u00b2-Net."""

    def __init__(self, spec: ModelSpec, model_path: Path) -> None:
        self.spec = spec
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelNotAvailableError("Berkas model tidak ditemukan. Unduh model terlebih dahulu.")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise BackgroundRemoverError(
                "ONNX Runtime belum terpasang. Jalankan: pip install -r requirements.txt"
            ) from exc

        options = ort.SessionOptions()
        options.log_severity_level = 3
        try:
            self._session = ort.InferenceSession(
                str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            if _is_memory_problem(exc):
                raise InsufficientMemoryError(
                    "Memori tidak cukup untuk memuat model AI. Tutup aplikasi lain lalu coba lagi, "
                    "atau pilih model yang lebih ringan."
                ) from exc
            log.error("Model gagal dimuat: %s", exc)
            raise ModelInvalidError(
                "Berkas model tidak valid atau rusak. Hapus dan unduh ulang model."
            ) from exc

        inputs = self._session.get_inputs()
        if not inputs or len(inputs[0].shape) != 4 or inputs[0].shape[1] not in (3, "3"):
            raise ModelInvalidError("Model tidak kompatibel. Input model harus berupa gambar RGB.")
        self._input_name = inputs[0].name
        height, width = inputs[0].shape[2], inputs[0].shape[3]
        if isinstance(height, int) and isinstance(width, int) and height > 0 and width > 0:
            self.size = (width, height)
        else:
            self.size = (spec.input_size, spec.input_size)
        self._mean = np.asarray(spec.mean, dtype=np.float32)
        self._std = np.asarray(spec.std, dtype=np.float32)

    def predict_mask(self, rgb: Image.Image) -> Image.Image:
        """Mengembalikan mask 'L' berukuran sama dengan gambar masukan (255 = objek)."""
        width, height = rgb.size
        small = rgb.convert("RGB").resize(self.size, Image.Resampling.LANCZOS)
        array = np.asarray(small, dtype=np.float32)
        peak = float(array.max()) if self.spec.normalize_by_max else 255.0
        array = array / max(peak, 1e-6)
        array = (array - self._mean) / self._std
        tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[np.newaxis, ...], dtype=np.float32)

        try:
            outputs = self._session.run(None, {self._input_name: tensor})
        except Exception as exc:
            if _is_memory_problem(exc):
                raise InsufficientMemoryError(
                    "Memori tidak cukup untuk memproses gambar ini. Coba gambar yang lebih kecil."
                ) from exc
            log.error("Inferensi gagal: %s", exc)
            raise ProcessingError("Model gagal memproses gambar ini.") from exc

        index = min(self.spec.output_index, len(outputs) - 1)
        prediction = np.squeeze(np.asarray(outputs[index], dtype=np.float32))
        if prediction.ndim != 2:
            raise ModelInvalidError("Keluaran model tidak sesuai. Model mungkin tidak kompatibel.")
        if not np.isfinite(prediction).all():
            raise ProcessingError("Model menghasilkan nilai tidak valid untuk gambar ini.")
        low, high = float(prediction.min()), float(prediction.max())
        if high - low > 1e-6:
            prediction = (prediction - low) / (high - low)
        else:
            prediction = np.clip(prediction, 0.0, 1.0)
        mask = Image.fromarray((prediction * 255.0).round().astype(np.uint8))
        return mask.resize((width, height), Image.Resampling.LANCZOS)


_cache_lock = threading.Lock()
_cache: dict[tuple, SegmentationSession] = {}


def get_session(spec: ModelSpec, model_path: Path) -> SegmentationSession:
    """Mengambil sesi dari cache. Hanya satu sesi disimpan agar memori tidak membengkak."""
    try:
        stat = os.stat(model_path)
    except OSError:
        raise ModelNotAvailableError("Berkas model tidak ditemukan. Unduh model terlebih dahulu.") from None
    key = (spec.model_id, str(model_path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        session = _cache.get(key)
        if session is None:
            _cache.clear()
            session = SegmentationSession(spec, Path(model_path))
            _cache[key] = session
        return session


def clear_session_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------- gambar

def _orient(image: Image.Image) -> Image.Image:
    """Menerapkan orientasi EXIF. Salinan penuh hanya dibuat bila rotasi memang diperlukan."""
    orientation = image.getexif().get(0x0112, 1)
    return ImageOps.exif_transpose(image) if orientation not in (0, 1) else image


def _to_rgb(image: Image.Image, warnings: list[str]) -> Image.Image:
    mode = image.mode
    if mode == "RGB":
        return image  # sudah RGB, tanpa salinan tambahan seukuran gambar
    if mode in ("RGBA", "LA") or (mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        warnings.append("Transparansi bawaan gambar diratakan pada latar putih sebelum diproses.")
        return Image.alpha_composite(white, rgba).convert("RGB")
    if mode.startswith("I") or mode == "F":
        array = np.asarray(image).astype(np.float32)
        peak = float(array.max()) if array.size else 0.0
        scale = 255.0 / (65535.0 if peak > 255 else 255.0)
        return Image.fromarray(np.clip(array * scale, 0, 255).astype(np.uint8)).convert("RGB")
    return image.convert("RGB")


def load_rgb(path: Path) -> tuple[Image.Image, list[str]]:
    """Membaca gambar masukan sebagai RGB (orientasi EXIF diterapkan). Mengembalikan (gambar, peringatan)."""
    info = inspect_image(path, SUPPORTED_EXTENSIONS, SUPPORTED_FORMATS, MAX_PIXELS)
    warnings: list[str] = []
    if info.frames > 1:
        warnings.append("Gambar beranimasi: hanya bingkai pertama yang diproses.")
    try:
        with Image.open(path) as source:
            source.load()  # setelah load(), gambar tetap valid walau berkas sudah ditutup
            return _to_rgb(_orient(source), warnings), warnings
    except UserMessageError:
        raise
    except MemoryError as exc:
        raise InsufficientMemoryError("Memori tidak cukup untuk membuka gambar ini.") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise UnsupportedImageError("Gambar rusak atau terpotong sehingga tidak dapat dibaca.") from exc


def remove_background(rgb: Image.Image, session: SegmentationSession) -> Image.Image:
    """Menghasilkan gambar RGBA dengan alpha dari mask model."""
    mask = session.predict_mask(rgb)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


# ---------------------------------------------------------------- latar pengganti

@dataclass(frozen=True)
class BackgroundOptions:
    mode: str = "transparent"  # transparent | color | image
    color: str = "#FFFFFF"
    image_path: str | None = None


def validate_options(options: BackgroundOptions) -> None:
    if options.mode not in MODES:
        raise ProcessingError("Mode latar belakang tidak dikenal.")
    if options.mode == "color" and not _HEX_COLOR.match(options.color or ""):
        raise ProcessingError("Warna latar tidak valid. Gunakan format #RRGGBB.")
    if options.mode == "image" and not options.image_path:
        raise ProcessingError("Pilih gambar untuk latar belakang terlebih dahulu.")


def load_background_image(path: str) -> Image.Image:
    """Memuat gambar latar pengganti sebagai RGBA."""
    rgb, _ = load_rgb(Path(path))
    return rgb.convert("RGBA")


def cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Mengisi seluruh area `size` dengan memotong bagian berlebih dari tengah (seperti CSS cover)."""
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def apply_background(rgba: Image.Image, options: BackgroundOptions, background: Image.Image | None = None) -> Image.Image:
    """Menerapkan mode latar. Hasil selalu RGBA agar kanal alpha selalu ada."""
    if options.mode == "color":
        base = Image.new("RGBA", rgba.size, options.color)
        base.alpha_composite(rgba)  # di tempat, tanpa salinan tambahan seukuran gambar
        return base
    if options.mode == "image":
        if background is None:
            raise ProcessingError("Gambar latar belakang belum dimuat.")
        base = cover_resize(background, rgba.size)  # selalu gambar baru, aman diubah di tempat
        base.alpha_composite(rgba)
        return base
    return rgba


# ---------------------------------------------------------------- pratinjau

def checkerboard(size: tuple[int, int], tile: int = 12) -> Image.Image:
    width, height = size
    yy, xx = np.indices((height, width))
    light = ((xx // tile) + (yy // tile)) % 2 == 0
    array = np.where(light[..., None], np.uint8(245), np.uint8(205)).astype(np.uint8)
    return Image.fromarray(np.repeat(array, 3, axis=2))


def composite_on_checkerboard(rgba: Image.Image, tile: int = 12) -> Image.Image:
    base = checkerboard(rgba.size, tile).convert("RGBA")
    return Image.alpha_composite(base, rgba.convert("RGBA"))


def load_preview(path: Path, max_side: int = 1400) -> Image.Image:
    """Memuat versi kecil gambar untuk pratinjau dengan cepat (JPEG memakai draft)."""
    try:
        with Image.open(path) as source:
            if source.format == "JPEG":
                source.draft("RGB", (max_side, max_side))
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except MemoryError as exc:
        raise InsufficientMemoryError("Memori tidak cukup untuk menampilkan pratinjau.") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise UnsupportedImageError("Pratinjau tidak dapat dibuat. Berkas hilang atau rusak.") from exc
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


# ---------------------------------------------------------------- batch

@dataclass
class ItemResult:
    source: Path
    status: str
    output: Path | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def process_batch(
    ctx: TaskContext,
    files: list[Path],
    output_dir: Path,
    session: SegmentationSession,
    options: BackgroundOptions,
    background: Image.Image | None = None,
    suffix: str = OUTPUT_SUFFIX,
) -> list[ItemResult]:
    """Memproses gambar satu per satu. Kegagalan satu gambar tidak menghentikan batch.

    Pembatalan berlaku di antara tahap dan antar gambar. Satu inferensi model yang sedang berjalan
    tidak dapat diputus, jadi pembatalan efektif setelah inferensi itu selesai.
    """
    total = len(files)
    results: list[ItemResult] = []
    for index, path in enumerate(files):
        ctx.check_cancel()
        base = index / total * 100
        span = 100 / total
        label = f"Memproses {index + 1} dari {total}: {path.name}"
        ctx.report(base, label)
        started = time.monotonic()
        output: Path | None = None
        try:
            rgb, warnings = load_rgb(path)
            ctx.check_cancel()
            ctx.report(base + span * 0.15, label)
            rgba = remove_background(rgb, session)
            del rgb  # lepaskan salinan RGB (3 byte per piksel) sebelum langkah berikutnya
            ctx.check_cancel()
            ctx.report(base + span * 0.8, label)
            final = apply_background(rgba, options, background)
            del rgba
            output = reserve_unique_path(Path(output_dir), sanitize_filename(path.stem) + suffix, ".png")
            if os.path.normcase(os.path.abspath(output)) == os.path.normcase(os.path.abspath(path)):
                raise ProcessingError("Hasil akan menimpa gambar asli. Pilih folder keluaran lain.")
            final.save(output, format="PNG")
            result = ItemResult(path, STATUS_OK, output, "", warnings, time.monotonic() - started)
        except OperationCancelled:
            discard_file(output)
            raise
        except UserMessageError as exc:
            discard_file(output)
            result = ItemResult(path, STATUS_FAILED, None, str(exc), [], time.monotonic() - started)
        except MemoryError:
            discard_file(output)
            result = ItemResult(
                path, STATUS_FAILED, None, "Memori tidak cukup untuk gambar ini.", [], time.monotonic() - started
            )
        except OSError:
            log.exception("Gagal menyimpan hasil untuk %s", path)
            discard_file(output)
            result = ItemResult(
                path, STATUS_FAILED, None,
                "Hasil gagal disimpan. Periksa ruang disk dan izin folder keluaran.", [], time.monotonic() - started,
            )
        except Exception:
            log.exception("Kesalahan tak terduga saat memproses %s", path)
            discard_file(output)
            result = ItemResult(
                path, STATUS_FAILED, None,
                "Terjadi kesalahan tak terduga pada gambar ini. Rincian teknis tersimpan di berkas log.", [],
                time.monotonic() - started,
            )
        results.append(result)
        ctx.emit_item(result)
    ctx.report(100, "Selesai")
    return results


def run_background_removal(
    ctx: TaskContext,
    manager: ModelManager,
    spec: ModelSpec,
    files: list[Path],
    output_dir: Path,
    options: BackgroundOptions,
) -> list[ItemResult]:
    """Fungsi pekerjaan lengkap untuk worker: validasi, muat model, lalu proses batch."""
    if not files:
        raise ProcessingError("Belum ada gambar yang dipilih.")
    validate_options(options)
    if manager.status(spec) != ModelStatus.PRESENT:
        raise ModelNotAvailableError("Model AI belum diunduh. Unduh model terlebih dahulu.")
    background = load_background_image(options.image_path) if options.mode == "image" else None
    ctx.report(0, "Memuat model AI...")
    session = get_session(spec, manager.path_for(spec))
    ctx.check_cancel()
    return process_batch(ctx, list(files), Path(output_dir), session, options, background)
