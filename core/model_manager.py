"""Pengunduh model generik: persetujuan eksplisit, progres, resume, dan verifikasi integritas.

Hanya memakai pustaka standar (urllib). Tidak pernah dipanggil tanpa consent=True.
"""

from __future__ import annotations

import errno
import hashlib
import http.client
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from core.logger import get_logger
from core.tasks import CancelToken, OperationCancelled, UserMessageError

log = get_logger("download")

USER_AGENT = "CreatorToolkit/0.1 (model downloader)"
CHUNK_SIZE = 64 * 1024
PROGRESS_INTERVAL = 0.1

ProgressCallback = Callable[[int, int | None], None]
StatusCallback = Callable[[str], None]


class DownloadError(UserMessageError):
    pass


class _SchemeLimitedRedirect(urllib.request.HTTPRedirectHandler):
    """Menolak pengalihan ke skema yang tidak diizinkan (misalnya dari HTTPS turun ke HTTP)."""

    def __init__(self, allowed_schemes: tuple[str, ...]) -> None:
        super().__init__()
        self._allowed = allowed_schemes

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if urlsplit(newurl).scheme not in self._allowed:
            raise DownloadError("Server mengarahkan unduhan ke alamat yang tidak aman. Unduhan dibatalkan.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ConsentRequiredError(DownloadError):
    pass


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    size: int
    resumed: bool
    verified: bool


def parse_checksum(spec: str) -> tuple[str, str]:
    """Memecah 'sha256:abcdef...' menjadi (algoritma, heksadesimal)."""
    algorithm, _, digest = spec.partition(":")
    algorithm = algorithm.strip().lower()
    digest = digest.strip().lower()
    if algorithm not in ("sha256", "sha1", "md5") or not digest or any(c not in "0123456789abcdef" for c in digest):
        raise DownloadError("Format checksum pada katalog model tidak valid.")
    return algorithm, digest


def hash_file(path: Path, algorithm: str, token: CancelToken | None = None) -> str:
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if token is not None:
                token.raise_if_cancelled()
            hasher.update(chunk)
    return hasher.hexdigest()


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    if exc.code == 404:
        return "Berkas model tidak ditemukan di server (kode 404). Alamat unduhan pada katalog mungkin sudah berubah."
    if exc.code in (401, 403):
        return f"Server menolak akses ke berkas model (kode {exc.code})."
    if exc.code == 429:
        return "Server membatasi permintaan unduhan (kode 429). Coba lagi beberapa saat lagi."
    if exc.code >= 500:
        return f"Server model sedang bermasalah (kode {exc.code}). Coba lagi nanti."
    return f"Server mengembalikan kesalahan (kode {exc.code})."


def _network_error_message(reason: object) -> str:
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "Waktu tunggu koneksi habis. Periksa koneksi internet lalu coba lagi."
    if isinstance(reason, ssl.SSLError):
        return "Sambungan aman (HTTPS) ke server gagal. Periksa tanggal komputer dan koneksi internet."
    if isinstance(reason, socket.gaierror):
        return "Server tidak dapat dijangkau. Periksa koneksi internet Anda."
    if isinstance(reason, ConnectionRefusedError):
        return "Koneksi ke server ditolak. Periksa koneksi internet atau coba lagi nanti."
    return "Tidak dapat terhubung ke server. Periksa koneksi internet Anda."


def _parse_content_range(value: str | None) -> tuple[int, int | None] | None:
    """Mengurai 'bytes 100-199/200' menjadi (awal, total)."""
    if not value or not value.startswith("bytes "):
        return None
    try:
        span, _, total = value[6:].partition("/")
        start = int(span.split("-")[0])
        return start, (int(total) if total.isdigit() else None)
    except ValueError:
        return None


def download_file(
    url: str,
    destination: Path,
    *,
    consent: bool,
    checksum: str | None = None,
    progress: ProgressCallback | None = None,
    status: StatusCallback | None = None,
    token: CancelToken | None = None,
    allowed_schemes: tuple[str, ...] = ("https",),
    timeout: float = 30.0,
) -> DownloadResult:
    """Mengunduh url ke destination lewat berkas .part, lalu memindahkannya setelah terverifikasi.

    Unduhan yang terputus dilanjutkan dari berkas .part saat dipanggil lagi.
    """
    if not consent:
        raise ConsentRequiredError("Unduhan memerlukan persetujuan pengguna.")
    token = token or CancelToken()
    parts = urlsplit(url)
    if parts.scheme not in allowed_schemes or not parts.netloc:
        raise DownloadError("Alamat unduhan tidak aman atau tidak valid. Hanya HTTPS yang diizinkan.")
    expected_hash = parse_checksum(checksum) if checksum else None

    destination = Path(destination)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"Folder penyimpanan model tidak dapat dibuat: {destination.parent}") from exc
    part = destination.with_name(destination.name + ".part")

    opener = urllib.request.build_opener(_SchemeLimitedRedirect(allowed_schemes))
    resumed = False
    for attempt in range(2):
        offset = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if offset > 0:
            request.add_header("Range", f"bytes={offset}-")
        token.raise_if_cancelled()
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and offset > 0 and attempt == 0:
                log.info("Server menolak Range, unduhan diulang dari awal.")
                part.unlink(missing_ok=True)
                continue
            raise DownloadError(_http_error_message(exc)) from exc
        except urllib.error.URLError as exc:
            raise DownloadError(_network_error_message(exc.reason)) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise DownloadError(_network_error_message(exc)) from exc
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            raise DownloadError(_network_error_message(exc)) from exc
        break

    with response:
        status_code = getattr(response, "status", 200)
        total: int | None = None
        mode = "wb"
        offset_used = 0
        if status_code == 206 and offset > 0:
            content_range = _parse_content_range(response.headers.get("Content-Range"))
            if content_range and content_range[0] == offset:
                mode, offset_used, resumed = "ab", offset, True
                total = content_range[1]
        if mode == "wb":
            length = response.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
        elif total is None:
            length = response.headers.get("Content-Length")
            total = offset_used + int(length) if length and length.isdigit() else None

        received = offset_used
        last_report = 0.0
        if status:
            status("Melanjutkan unduhan..." if resumed else "Mengunduh...")
        try:
            with open(part, mode) as handle:
                while True:
                    token.raise_if_cancelled()
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
                    now = time.monotonic()
                    if progress and now - last_report >= PROGRESS_INTERVAL:
                        last_report = now
                        progress(received, total)
        except OperationCancelled:
            raise
        except OSError as exc:
            if isinstance(exc, ssl.SSLError):
                raise DownloadError(_network_error_message(exc)) from exc
            if exc.errno == errno.ENOSPC:
                raise DownloadError("Ruang disk tidak cukup untuk menyimpan model.") from exc
            if isinstance(exc, (ConnectionError, socket.timeout, TimeoutError)):
                raise DownloadError(
                    "Koneksi terputus saat mengunduh. Unduhan dapat dilanjutkan dari bagian yang sudah tersimpan."
                ) from exc
            raise DownloadError("Berkas model gagal ditulis. Periksa izin dan ruang disk.") from exc
        except (http.client.IncompleteRead, http.client.HTTPException) as exc:
            raise DownloadError(
                "Koneksi terputus saat mengunduh. Unduhan dapat dilanjutkan dari bagian yang sudah tersimpan."
            ) from exc

    if progress:
        progress(received, total)
    if total is not None and received != total:
        raise DownloadError(
            f"Unduhan tidak lengkap ({received} dari {total} byte). Coba lagi untuk melanjutkan."
        )
    if received == 0:
        part.unlink(missing_ok=True)
        raise DownloadError("Server mengirim berkas kosong.")

    verified = False
    if expected_hash:
        if status:
            status("Memverifikasi integritas berkas...")
        algorithm, digest = expected_hash
        actual = hash_file(part, algorithm, token)
        if actual != digest:
            part.unlink(missing_ok=True)
            raise DownloadError(
                "Berkas yang diunduh tidak cocok dengan checksum (rusak atau telah berubah). "
                "Berkas dihapus. Silakan coba unduh lagi."
            )
        verified = True

    try:
        os.replace(part, destination)
    except OSError as exc:
        raise DownloadError("Model sudah diunduh tetapi gagal dipindahkan ke folder tujuan.") from exc
    return DownloadResult(path=destination, size=received, resumed=resumed, verified=verified)
