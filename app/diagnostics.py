"""Pemeriksaan lingkungan dan dependensi."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from importlib import metadata

# (nama paket distribusi, nama modul untuk import)
REQUIRED_PACKAGES: list[tuple[str, str]] = [
    ("PySide6", "PySide6"),
    ("Pillow", "PIL"),
    ("qrcode", "qrcode"),
    ("numpy", "numpy"),
    ("onnxruntime", "onnxruntime"),
]


@dataclass(frozen=True)
class PackageStatus:
    distribution: str
    module: str
    installed: bool
    version: str | None


def check_packages() -> list[PackageStatus]:
    """Memeriksa keberadaan paket tanpa mengimpor modul berat seperti onnxruntime."""
    results: list[PackageStatus] = []
    for distribution, module in REQUIRED_PACKAGES:
        installed = importlib.util.find_spec(module) is not None
        version: str | None = None
        if installed:
            try:
                version = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                version = None
        results.append(PackageStatus(distribution, module, installed, version))
    return results


def format_report() -> str:
    lines = [f"Python {sys.version.split()[0]} pada {sys.platform}"]
    for status in check_packages():
        if status.installed:
            lines.append(f"  [OK] {status.distribution} {status.version or ''}".rstrip())
        else:
            lines.append(f"  [BELUM TERPASANG] {status.distribution}")
    return "\n".join(lines)
