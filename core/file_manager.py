"""Pengelola berkas: validasi gambar, ekspansi jalur, nama aman, dan penamaan unik tanpa menimpa."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

from core.tasks import UserMessageError

DEFAULT_STEM = "berkas"
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class FileOperationError(UserMessageError):
    pass


class InvalidImageError(FileOperationError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    path: Path
    width: int
    height: int
    format: str
    frames: int


def sanitize_filename(name: str, default: str = DEFAULT_STEM) -> str:
    """Membersihkan nama berkas agar valid di Windows. Spasi dan huruf non-ASCII dipertahankan."""
    cleaned = _INVALID_CHARS.sub("_", name or "").strip().strip(".")
    cleaned = cleaned[:120].rstrip(" .")
    if not cleaned:
        return default
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def reserve_unique_path(directory: Path, stem: str, extension: str) -> Path:
    """Membuat berkas kosong bernama unik. Berkas yang sudah ada tidak pernah ditimpa."""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        raise FileOperationError("Jalur folder keluaran adalah sebuah berkas, bukan folder.") from None
    except PermissionError:
        raise FileOperationError(f"Tidak ada izin membuat folder: {directory}") from None
    except OSError as exc:
        raise FileOperationError(f"Folder keluaran tidak dapat dibuat: {directory}") from exc

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
            raise FileOperationError(f"Tidak ada izin menulis ke folder: {directory}") from None
        except OSError as exc:
            raise FileOperationError(f"Berkas keluaran tidak dapat dibuat di: {directory}") from exc
    raise FileOperationError("Terlalu banyak berkas dengan nama yang sama di folder tujuan.")


def discard_file(path: Path | None) -> None:
    """Menghapus berkas hasil yang tidak lengkap. Gagal menghapus diabaikan."""
    if path is None:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def expand_paths(paths: Iterable[str | Path], extensions: set[str]) -> list[Path]:
    """Mengubah daftar berkas dan folder menjadi daftar berkas unik. Folder dibaca satu tingkat."""
    result: list[Path] = []
    seen: set[str] = set()

    def add(candidate: Path) -> None:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen:
            seen.add(key)
            result.append(candidate)

    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            try:
                children = sorted(child for child in path.iterdir() if child.is_file())
            except OSError:
                continue
            for child in children:
                if child.suffix.lower() in extensions:
                    add(child)
        else:
            add(path)
    return result


def inspect_image(
    path: Path,
    allowed_extensions: set[str],
    allowed_formats: set[str],
    max_pixels: int,
) -> ImageInfo:
    """Memeriksa ekstensi dan format asli berkas tanpa memuat seluruh piksel."""
    path = Path(path)
    if path.suffix.lower() not in allowed_extensions:
        allowed = ", ".join(sorted(ext.lstrip(".").upper() for ext in allowed_extensions))
        raise InvalidImageError(f"Ekstensi {path.suffix or '(kosong)'} tidak didukung. Gunakan: {allowed}.")
    if not path.exists():
        raise InvalidImageError("Berkas tidak ditemukan.")
    if not path.is_file():
        raise InvalidImageError("Jalur ini bukan sebuah berkas.")
    try:
        with Image.open(path) as image:
            fmt = image.format or ""
            width, height = image.size
            frames = getattr(image, "n_frames", 1)
            if fmt not in allowed_formats:
                raise InvalidImageError(f"Format gambar {fmt or 'tidak dikenal'} tidak didukung.")
            if width * height > max_pixels:
                raise InvalidImageError(
                    f"Gambar terlalu besar ({width * height / 1e6:.0f} megapiksel, maksimal {max_pixels / 1e6:.0f})."
                )
            image.verify()
    except InvalidImageError:
        raise
    except PermissionError:
        raise InvalidImageError("Tidak ada izin membaca berkas ini.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Berkas bukan gambar yang valid atau rusak.") from exc
    return ImageInfo(path=path, width=width, height=height, format=fmt, frames=frames)
