"""Mesin pembuat QR: matriks, pewarnaan, logo, dan pemeriksaan keterbacaan. Tanpa Qt."""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageOps, UnidentifiedImageError

from modules.qr_generator import payloads, validator

MIN_SIZE = 128
MAX_SIZE = 4096
MIN_BORDER = 0
MAX_BORDER = 20
STANDARD_BORDER = 4
EC_LEVELS = ("L", "M", "Q", "H")

# Batas sisi area logo (termasuk bantalan) terhadap sisi area modul QR.
# Dipilih konservatif agar area tertutup jauh di bawah kapasitas koreksi kesalahan.
MAX_LOGO_RATIO = {"L": 0.0, "M": 0.15, "Q": 0.20, "H": 0.25}
DEFAULT_LOGO_RATIO = 0.20
LOGO_PADDING = 0.08
MAX_LOGO_BYTES = 20 * 1024 * 1024
LOGO_STORE_DIMENSION = 1024
ALLOWED_LOGO_FORMATS = {"PNG", "JPEG", "WEBP", "BMP", "GIF"}
DENSE_MODULES = 57  # versi 10
MIN_MODULE_PX = 3
LOW_CONTRAST = 3.0

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class QRError(Exception):
    """Dasar semua error mesin QR. Pesan selalu aman ditampilkan kepada pengguna."""


class QRValidationError(QRError):
    def __init__(self, field_errors: Mapping[str, str], setting_errors: Mapping[str, str]) -> None:
        self.field_errors = dict(field_errors)
        self.setting_errors = dict(setting_errors)
        messages = list(self.field_errors.values()) + list(self.setting_errors.values())
        super().__init__(" ".join(messages) or "Input tidak valid.")


class QRGenerationError(QRError):
    pass


@dataclass(frozen=True)
class QRSettings:
    foreground: str = "#000000"
    background: str = "#FFFFFF"
    size_px: int = 512
    error_correction: str = "M"
    border: int = STANDARD_BORDER
    logo_path: str | None = None
    logo_ratio: float = DEFAULT_LOGO_RATIO


@dataclass
class LogoOverlay:
    plate_box: tuple[int, int, int, int]  # x, y, lebar, tinggi (piksel)
    logo_box: tuple[int, int, int, int]
    logo_image: Image.Image  # RGBA, sudah berukuran logo_box
    modules: int


@dataclass
class QRResult:
    payload: str
    matrix: list[list[bool]]
    image: Image.Image
    settings: QRSettings
    module_px: int
    version: int
    warnings: list[str] = field(default_factory=list)
    logo: LogoOverlay | None = None
    final_size_px: int = 0  # ukuran hasil ekspor sebenarnya, berbeda dari image bila ini hasil pratinjau
    preview_only: bool = False  # True bila gambar dirender lebih kecil untuk pratinjau dan tidak boleh diekspor

    @property
    def size_px(self) -> int:
        return self.image.size[0]

    @property
    def modules(self) -> int:
        return len(self.matrix)


# ---------------------------------------------------------------- warna

def parse_hex(color: str) -> tuple[int, int, int]:
    if not _HEX_COLOR.match(color):
        raise ValueError(f"Warna tidak valid: {color}")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a: str, color_b: str) -> float:
    la = relative_luminance(parse_hex(color_a))
    lb = relative_luminance(parse_hex(color_b))
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------- pengaturan

def max_logo_ratio(error_correction: str) -> float:
    return MAX_LOGO_RATIO.get(error_correction, 0.0)


def validate_settings(settings: QRSettings) -> tuple[dict[str, str], list[str]]:
    """Mengembalikan (kesalahan per pengaturan, peringatan)."""
    errors: dict[str, str] = {}
    warnings: list[str] = []

    for key, label in (("foreground", "depan"), ("background", "latar")):
        if not _HEX_COLOR.match(getattr(settings, key) or ""):
            errors[key] = f"Warna {label} tidak valid. Gunakan format #RRGGBB."
    if not MIN_SIZE <= settings.size_px <= MAX_SIZE:
        errors["size"] = f"Ukuran harus antara {MIN_SIZE} dan {MAX_SIZE} piksel."
    if settings.error_correction not in EC_LEVELS:
        errors["error_correction"] = "Tingkat koreksi kesalahan tidak dikenal."
    if not MIN_BORDER <= settings.border <= MAX_BORDER:
        errors["border"] = f"Zona tenang harus antara {MIN_BORDER} dan {MAX_BORDER} modul."

    if "foreground" not in errors and "background" not in errors:
        fg, bg = settings.foreground, settings.background
        if fg.upper() == bg.upper():
            errors["foreground"] = "Warna depan dan latar tidak boleh sama."
        else:
            ratio = contrast_ratio(fg, bg)
            if relative_luminance(parse_hex(fg)) > relative_luminance(parse_hex(bg)):
                warnings.append(
                    "Warna depan lebih terang daripada latar (terbalik). Sebagian pemindai gagal membacanya."
                )
            if ratio < LOW_CONTRAST:
                warnings.append(
                    f"Kontras warna rendah ({ratio:.1f} banding 1). Kode QR dapat sulit dipindai. "
                    f"Gunakan kontras minimal {LOW_CONTRAST:.0f} banding 1."
                )

    if "border" not in errors and settings.border < STANDARD_BORDER:
        warnings.append(
            f"Zona tenang {settings.border} modul lebih kecil dari standar {STANDARD_BORDER} modul. "
            "Pemindai dapat gagal membaca kode."
        )

    if settings.logo_path and "error_correction" not in errors:
        if max_logo_ratio(settings.error_correction) <= 0:
            errors["logo"] = "Logo membutuhkan koreksi kesalahan M atau lebih tinggi."
    return errors, warnings


# ---------------------------------------------------------------- logo

def _read_logo(path: str) -> Image.Image:
    try:
        with Image.open(path) as source:
            if source.format not in ALLOWED_LOGO_FORMATS:
                raise QRGenerationError("Format logo tidak didukung. Gunakan PNG, JPG, WEBP, BMP, atau GIF.")
            rgba = ImageOps.exif_transpose(source).convert("RGBA")
    except QRGenerationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise QRGenerationError(
            "Berkas logo tidak dapat dibaca. Pastikan berkas adalah gambar yang valid dan tidak rusak."
        ) from exc
    rgba.thumbnail((LOGO_STORE_DIMENSION, LOGO_STORE_DIMENSION), Image.Resampling.LANCZOS)
    return rgba


@functools.lru_cache(maxsize=4)
def _read_logo_cached(path: str, mtime_ns: int, size: int) -> Image.Image:
    return _read_logo(path)


def load_logo(path: str) -> Image.Image:
    """Memuat logo dengan cache. Gambar yang dikembalikan tidak boleh diubah langsung."""
    file_path = Path(path)
    try:
        stat = file_path.stat()
    except FileNotFoundError:
        raise QRGenerationError(f"Berkas logo tidak ditemukan: {file_path.name}") from None
    except OSError as exc:
        raise QRGenerationError("Berkas logo tidak dapat diakses.") from exc
    if not file_path.is_file():
        raise QRGenerationError("Jalur logo bukan sebuah berkas.")
    if stat.st_size > MAX_LOGO_BYTES:
        raise QRGenerationError("Berkas logo terlalu besar (maksimal 20 MB).")
    return _read_logo_cached(str(file_path), stat.st_mtime_ns, stat.st_size)


def logo_modules_for(modules: int, ratio: float, error_correction: str) -> int:
    """Jumlah modul sisi area logo. Paritas disamakan dengan jumlah modul agar logo tepat di tengah."""
    limit = math.floor(max_logo_ratio(error_correction) * modules)
    target = min(round(ratio * modules), limit)
    if (modules - target) % 2:
        target -= 1
    return target if target >= 3 else 0


# ---------------------------------------------------------------- matriks dan render

@functools.lru_cache(maxsize=16)
def _matrix_cached(payload: str, error_correction: str) -> tuple[tuple[tuple[bool, ...], ...], int]:
    import qrcode
    from qrcode import constants
    from qrcode.exceptions import DataOverflowError

    levels = {
        "L": constants.ERROR_CORRECT_L,
        "M": constants.ERROR_CORRECT_M,
        "Q": constants.ERROR_CORRECT_Q,
        "H": constants.ERROR_CORRECT_H,
    }
    code = qrcode.QRCode(version=None, error_correction=levels[error_correction], box_size=1, border=0)
    try:
        code.add_data(payload)
        code.make(fit=True)
    except (DataOverflowError, ValueError) as exc:
        raise QRGenerationError(
            "Isi terlalu panjang untuk satu kode QR pada tingkat koreksi ini. "
            "Persingkat isi atau turunkan tingkat koreksi kesalahan."
        ) from exc
    matrix = tuple(tuple(bool(cell) for cell in row) for row in code.get_matrix())
    return matrix, int(code.version)


def create_matrix(payload: str, error_correction: str) -> tuple[tuple[tuple[bool, ...], ...], int]:
    """Membuat matriks modul QR (tanpa zona tenang) memakai pustaka qrcode.

    Hasilnya di-cache karena pembuatan matriks adalah bagian paling lambat. Mengubah warna, ukuran, atau
    zona tenang tidak perlu menghitung ulang matriks.
    """
    return _matrix_cached(payload, error_correction)


def render_image(
    matrix: list[list[bool]],
    settings: QRSettings,
    logo: Image.Image | None = None,
    logo_modules: int = 0,
) -> tuple[Image.Image, int, LogoOverlay | None]:
    """Merender matriks menjadi gambar RGB. Setiap modul berukuran bulat agar tepi tajam."""
    n = len(matrix)
    total = n + 2 * settings.border
    module_px = max(1, round(settings.size_px / total))

    mask = Image.new("L", (n, n), 0)
    mask.putdata([255 if cell else 0 for row in matrix for cell in row])
    mask = mask.resize((n * module_px, n * module_px), Image.Resampling.NEAREST)

    canvas = Image.new("RGB", (total * module_px, total * module_px), parse_hex(settings.background))
    origin = settings.border * module_px
    canvas.paste(parse_hex(settings.foreground), (origin, origin), mask)

    overlay: LogoOverlay | None = None
    if logo is not None and logo_modules >= 3:
        plate_px = logo_modules * module_px
        plate_x = plate_y = origin + ((n - logo_modules) // 2) * module_px
        canvas.paste(parse_hex(settings.background), (plate_x, plate_y, plate_x + plate_px, plate_y + plate_px))

        inner = max(1, int(plate_px * (1 - 2 * LOGO_PADDING)))
        scale = min(inner / logo.width, inner / logo.height)
        width, height = max(1, round(logo.width * scale)), max(1, round(logo.height * scale))
        resized = logo.resize((width, height), Image.Resampling.LANCZOS)
        logo_x = plate_x + (plate_px - width) // 2
        logo_y = plate_y + (plate_px - height) // 2
        canvas.paste(resized, (logo_x, logo_y), resized)
        overlay = LogoOverlay(
            plate_box=(plate_x, plate_y, plate_px, plate_px),
            logo_box=(logo_x, logo_y, width, height),
            logo_image=resized,
            modules=logo_modules,
        )
    return canvas, module_px, overlay


def generate_from_payload(
    payload: str,
    settings: QRSettings,
    extra_warnings: list[str] | None = None,
    render_size_px: int | None = None,
) -> QRResult:
    """Membuat QR dari teks payload dan pengaturan tampilan.

    render_size_px membatasi ukuran gambar yang dirender (untuk pratinjau agar cepat dan hemat memori).
    Hasilnya ditandai preview_only dan tidak dapat diekspor. Peringatan tetap dihitung dari ukuran akhir.
    """
    errors, warnings = validate_settings(settings)
    if errors:
        raise QRValidationError({}, errors)
    warnings = list(extra_warnings or []) + warnings

    matrix, version = create_matrix(payload, settings.error_correction)
    modules = len(matrix)

    logo_image: Image.Image | None = None
    logo_modules = 0
    if settings.logo_path:
        logo_image = load_logo(settings.logo_path)
        logo_modules = logo_modules_for(modules, settings.logo_ratio, settings.error_correction)
        if logo_modules == 0:
            raise QRGenerationError(
                "Kode QR terlalu kecil untuk memuat logo dengan aman. "
                "Perpanjang isi atau naikkan tingkat koreksi kesalahan."
            )

    capped = render_size_px is not None and render_size_px < settings.size_px
    render_settings = replace(settings, size_px=render_size_px) if capped else settings
    image, module_px, overlay = render_image(matrix, render_settings, logo_image, logo_modules)

    total = modules + 2 * settings.border
    final_module_px = max(1, round(settings.size_px / total))
    if final_module_px < MIN_MODULE_PX:
        warnings.append(
            f"Setiap modul hanya {final_module_px} piksel. Perbesar ukuran agar kode mudah dipindai."
        )
    if modules > DENSE_MODULES:
        warnings.append("Isi yang panjang menghasilkan kode padat yang lebih sulit dipindai. Pertimbangkan memperpendek isi.")

    return QRResult(
        payload=payload,
        matrix=matrix,
        image=image,
        settings=settings,
        module_px=module_px,
        version=version,
        warnings=warnings,
        logo=overlay,
        final_size_px=final_module_px * total,
        preview_only=capped,
    )


def generate_qr(
    type_id: str,
    values: Mapping[str, Any],
    settings: QRSettings,
    render_size_px: int | None = None,
) -> QRResult:
    """Alur utama: validasi isian dan pengaturan, bangun payload, lalu render QR."""
    validation = validator.validate(type_id, values)
    setting_errors, _ = validate_settings(settings)
    if validation.errors or setting_errors:
        raise QRValidationError(validation.errors, setting_errors)
    payload = payloads.build_payload(type_id, validation.normalized)
    return generate_from_payload(payload, settings, extra_warnings=validation.warnings, render_size_px=render_size_px)
