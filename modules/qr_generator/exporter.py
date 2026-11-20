"""Ekspor hasil QR ke PNG, JPG, SVG, dan PDF. Tanpa Qt."""

from __future__ import annotations

import base64
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from modules.qr_generator.processor import QRResult

FORMATS: dict[str, str] = {"PNG": ".png", "JPG": ".jpg", "SVG": ".svg", "PDF": ".pdf"}
PDF_DPI = 300.0
DEFAULT_STEM = "qr-code"
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ExportError(Exception):
    """Error ekspor dengan pesan Indonesia yang aman ditampilkan."""


@dataclass
class ExportResult:
    path: Path
    format: str
    size_px: int
    warnings: list[str] = field(default_factory=list)


def sanitize_filename(name: str) -> str:
    """Membersihkan nama berkas agar valid di Windows. Karakter Indonesia dan spasi dipertahankan."""
    cleaned = _INVALID_CHARS.sub("_", name or "").strip().strip(".")
    cleaned = cleaned[:120].rstrip(" .")
    if not cleaned:
        return DEFAULT_STEM
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def reserve_unique_path(directory: Path, stem: str, extension: str) -> Path:
    """Membuat berkas kosong dengan nama unik. Berkas yang sudah ada tidak pernah ditimpa."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        raise ExportError("Jalur folder keluaran adalah sebuah berkas, bukan folder.") from None
    except PermissionError:
        raise ExportError(f"Tidak ada izin membuat folder: {directory}") from None
    except OSError as exc:
        raise ExportError(f"Folder keluaran tidak dapat dibuat: {directory}") from exc

    for index in range(10_000):
        name = f"{stem}{extension}" if index == 0 else f"{stem} ({index}){extension}"
        candidate = directory / name
        try:
            with open(candidate, "xb"):
                pass
            return candidate
        except FileExistsError:
            continue
        except PermissionError:
            raise ExportError(f"Tidak ada izin menulis ke folder: {directory}") from None
        except OSError as exc:
            raise ExportError(f"Berkas keluaran tidak dapat dibuat di: {directory}") from exc
    raise ExportError("Terlalu banyak berkas dengan nama yang sama di folder tujuan.")


def build_svg(result: QRResult) -> str:
    """SVG vektor: satu path untuk semua modul gelap, ditambah logo bila ada."""
    n = result.modules
    border = result.settings.border
    total = n + 2 * border
    px = result.size_px
    fg, bg = result.settings.foreground, result.settings.background

    segments: list[str] = []
    for y, row in enumerate(result.matrix):
        x = 0
        while x < n:
            if row[x]:
                start = x
                while x < n and row[x]:
                    x += 1
                length = x - start
                segments.append(f"M{start + border} {y + border}h{length}v1h-{length}z")
            else:
                x += 1

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{px}" height="{px}" viewBox="0 0 {total} {total}" shape-rendering="crispEdges">',
        f'<rect width="{total}" height="{total}" fill="{bg}"/>',
        f'<path fill="{fg}" d="{"".join(segments)}"/>',
    ]
    if result.logo is not None:
        unit = result.module_px

        def units(value: int) -> str:
            return f"{value / unit:.4f}".rstrip("0").rstrip(".")

        px_, py_, pw, ph = result.logo.plate_box
        lx, ly, lw, lh = result.logo.logo_box
        buffer = io.BytesIO()
        result.logo.logo_image.save(buffer, format="PNG")
        data = base64.b64encode(buffer.getvalue()).decode("ascii")
        parts.append(
            f'<rect id="logo-plate" x="{units(px_)}" y="{units(py_)}" '
            f'width="{units(pw)}" height="{units(ph)}" fill="{bg}"/>'
        )
        parts.append(
            f'<image id="logo" x="{units(lx)}" y="{units(ly)}" width="{units(lw)}" height="{units(lh)}" '
            f'xlink:href="data:image/png;base64,{data}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _save_raster(result: QRResult, path: Path, fmt: str) -> None:
    image = result.image
    if fmt == "PNG":
        image.save(path, format="PNG", optimize=True)
    elif fmt == "JPG":
        image.convert("RGB").save(path, format="JPEG", quality=95, subsampling=0)
    elif fmt == "PDF":
        # Palet 256 warna dikompresi tanpa kehilangan kualitas (Flate), bukan JPEG.
        palette_image = image.convert("RGB").quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
        palette_image.save(path, format="PDF", resolution=PDF_DPI)


def export_qr(result: QRResult, directory: str | Path, stem: str, fmt: str) -> ExportResult:
    """Menyimpan QR ke folder tujuan dengan nama unik. Folder dibuat bila belum ada."""
    if result.preview_only:
        raise ExportError("Gambar pratinjau tidak dapat diekspor. Buat ulang QR pada ukuran penuh.")
    fmt = fmt.upper()
    if fmt not in FORMATS:
        raise ExportError("Format ekspor tidak dikenal. Pilih PNG, JPG, SVG, atau PDF.")

    path = reserve_unique_path(Path(directory), sanitize_filename(stem), FORMATS[fmt])
    try:
        if fmt == "SVG":
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(build_svg(result))
        else:
            _save_raster(result, path, fmt)
    except PermissionError:
        _discard(path)
        raise ExportError(f"Tidak ada izin menulis ke: {path.parent}") from None
    except OSError as exc:
        _discard(path)
        raise ExportError(
            "Berkas gagal disimpan. Periksa ruang disk dan izin folder tujuan."
        ) from exc
    except Exception as exc:
        _discard(path)
        raise ExportError("Berkas gagal dibuat. Rincian teknis tersimpan di berkas log.") from exc

    warnings: list[str] = []
    if fmt == "JPG":
        warnings.append("JPG memakai kompresi lossy. Untuk hasil paling tajam, gunakan PNG atau SVG.")
    if fmt == "PDF":
        warnings.append("PDF berisi gambar QR beresolusi 300 dpi, bukan vektor. Gunakan SVG untuk vektor.")
    return ExportResult(path=path, format=fmt, size_px=result.size_px, warnings=warnings)


def _discard(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
