"""Model tampilan riwayat. Tanpa Qt agar dapat diuji."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Callable

from core.database import STATUS_FAILED, HistoryDatabase, HistoryEntry, HistoryError

MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
KIND_OK = "ok"
KIND_FAILED = "failed"
KIND_MISSING = "missing"


@dataclass(frozen=True)
class RowInfo:
    entry_id: int
    tool: str
    title: str
    detail: str
    when: str
    status_text: str
    status_kind: str
    folder: Path | None
    can_open: bool
    path: str = ""


def format_time(moment: datetime, now: datetime | None = None, tz: tzinfo | None = None) -> str:
    local = moment.astimezone(tz)
    current = (now or datetime.now(timezone.utc)).astimezone(tz)
    clock = local.strftime("%H:%M")
    days = (current.date() - local.date()).days
    if days == 0:
        return f"Hari ini {clock}"
    if days == 1:
        return f"Kemarin {clock}"
    return f"{local.day} {MONTHS[local.month - 1]} {local.year} {clock}"


def shorten_middle(text: str, limit: int = 56) -> str:
    """Memendekkan teks panjang dengan elipsis di tengah agar awal dan akhir nama tetap terlihat."""
    if len(text) <= limit or limit < 5:
        return text
    head = (limit - 1) // 2
    tail = limit - 1 - head
    return f"{text[:head]}\u2026{text[len(text) - tail:]}"


def _exists(path: str | Path) -> bool:
    try:
        return os.path.exists(path)
    except OSError:
        return False


def describe(
    entry: HistoryEntry,
    now: datetime | None = None,
    tz: tzinfo | None = None,
    exists: Callable[[str | Path], bool] = _exists,
) -> RowInfo:
    """Mengubah satu catatan menjadi baris tampilan, termasuk deteksi berkas yang hilang."""
    shown = entry.output_file or entry.input_file
    title = Path(shown).name if shown else "(tanpa berkas)"
    source = entry.output_file or entry.input_file
    folder = Path(source).parent if source else None
    can_open = folder is not None and exists(folder)

    if entry.status == STATUS_FAILED:
        kind, text = KIND_FAILED, "Gagal diproses"
        detail = str(entry.input_file or "")
    elif entry.output_file and not exists(entry.output_file):
        kind, text = KIND_MISSING, "Berkas tidak ditemukan"
        detail = str(folder or "")
    else:
        kind, text = KIND_OK, "Berhasil"
        detail = str(folder or "")
    return RowInfo(
        entry_id=entry.id,
        tool=entry.tool_name,
        title=shorten_middle(title),
        detail=shorten_middle(detail, 64),
        when=format_time(entry.created_at, now, tz),
        status_text=text,
        status_kind=kind,
        folder=folder,
        can_open=can_open,
        path=str(shown or ""),
    )


def load_rows(history: HistoryDatabase | None, limit: int) -> list[RowInfo] | None:
    """Memuat baris tampilan. Mengembalikan None bila riwayat tidak tersedia."""
    if history is None:
        return None
    try:
        return [describe(entry) for entry in history.recent(limit)]
    except HistoryError:
        return None
