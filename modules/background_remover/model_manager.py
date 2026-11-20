"""Katalog model dan pengelola model Background Remover."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from core import model_manager as downloader
from core.logger import get_logger
from core.tasks import CancelToken

log = get_logger("bg.models")

_RELEASE_BASE = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
DEFAULT_MODEL_ID = "u2net"
CATALOG_FILE = "catalog.json"
_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.onnx$")


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    filename: str
    url: str
    description: str = ""
    approx_size_mb: int | None = None
    checksum: str | None = None  # 'sha256:...' atau 'md5:...', diisi hanya bila sudah diverifikasi dari sumber resmi
    license_note: str = ""
    input_size: int = 320
    mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    normalize_by_max: bool = True
    output_index: int = 0

    @property
    def source_host(self) -> str:
        return downloader.urlsplit(self.url).netloc


# Alamat dan ukuran berasal dari pengetahuan umum tentang rilis rembg dan BELUM diverifikasi
# dari jaringan. Checksum sengaja dikosongkan sampai nilai resmi diverifikasi.
DEFAULT_CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        "u2net",
        "U\u00b2-Net (umum, akurat)",
        "u2net.onnx",
        _RELEASE_BASE + "u2net.onnx",
        "Model serbaguna untuk orang, produk, dan objek. Ukuran besar dan lebih lambat di CPU.",
        approx_size_mb=176,
        license_note="U\u00b2-Net: Apache-2.0 (perlu diverifikasi)",
    ),
    ModelSpec(
        "u2netp",
        "U\u00b2-Net ringan (cepat, kurang akurat)",
        "u2netp.onnx",
        _RELEASE_BASE + "u2netp.onnx",
        "Versi kecil dan cepat. Cocok untuk uji coba, tepi objek kurang rapi.",
        approx_size_mb=5,
        license_note="U\u00b2-Net: Apache-2.0 (perlu diverifikasi)",
    ),
    ModelSpec(
        "silueta",
        "Silueta (ukuran menengah)",
        "silueta.onnx",
        _RELEASE_BASE + "silueta.onnx",
        "Turunan U\u00b2-Net yang lebih kecil dengan hasil umum yang baik.",
        approx_size_mb=43,
        license_note="Lisensi perlu diverifikasi sebelum distribusi",
    ),
)


class ModelStatus(Enum):
    MISSING = "missing"
    PARTIAL = "partial"
    PRESENT = "present"


def format_size(num_bytes: float) -> str:
    megabytes = num_bytes / (1024 * 1024)
    if megabytes >= 10:
        return f"{megabytes:.0f} MB"
    return f"{megabytes:.1f} MB".replace(".", ",")


def _spec_from_dict(entry: dict) -> ModelSpec | None:
    try:
        filename = str(entry["filename"])
        url = str(entry["url"])
        if not _FILENAME.match(filename):
            raise ValueError("nama berkas tidak valid")
        if not url.lower().startswith("https://"):
            raise ValueError("url harus HTTPS")
        input_size = int(entry.get("input_size", 320))
        if not 64 <= input_size <= 4096:
            raise ValueError("input_size di luar rentang")
        mean = tuple(float(v) for v in entry.get("mean", (0.485, 0.456, 0.406)))
        std = tuple(float(v) for v in entry.get("std", (0.229, 0.224, 0.225)))
        if len(mean) != 3 or len(std) != 3 or any(v <= 0 for v in std):
            raise ValueError("mean dan std harus berisi 3 angka, std positif")
        checksum = entry.get("checksum") or None
        if checksum:
            downloader.parse_checksum(str(checksum))
        size = entry.get("approx_size_mb")
        return ModelSpec(
            model_id=str(entry["model_id"]),
            display_name=str(entry["display_name"]),
            filename=filename,
            url=url,
            description=str(entry.get("description", "")),
            approx_size_mb=int(size) if size is not None else None,
            checksum=str(checksum) if checksum else None,
            license_note=str(entry.get("license_note", "")),
            input_size=input_size,
            mean=mean,  # type: ignore[arg-type]
            std=std,  # type: ignore[arg-type]
            normalize_by_max=bool(entry.get("normalize_by_max", True)),
            output_index=int(entry.get("output_index", 0)),
        )
    except (KeyError, ValueError, TypeError, downloader.DownloadError) as exc:
        log.warning("Entri katalog model dilewati: %s", exc)
        return None


def load_catalog(models_dir: Path) -> list[ModelSpec]:
    """Katalog bawaan digabung dengan catalog.json buatan pengguna (menambah atau mengganti model_id)."""
    catalog = {spec.model_id: spec for spec in DEFAULT_CATALOG}
    extra_path = Path(models_dir) / CATALOG_FILE
    if extra_path.is_file():
        try:
            data = json.loads(extra_path.read_text(encoding="utf-8"))
            for entry in data.get("models", []):
                spec = _spec_from_dict(entry) if isinstance(entry, dict) else None
                if spec:
                    catalog[spec.model_id] = spec
        except (OSError, ValueError, AttributeError) as exc:
            log.warning("catalog.json tidak dapat dibaca: %s", exc)
    return list(catalog.values())


class ModelManager:
    """Mengelola lokasi, status, dan unduhan model di folder data aplikasi."""

    def __init__(self, models_dir: Path, catalog: list[ModelSpec] | None = None) -> None:
        self.models_dir = Path(models_dir)
        self.catalog = catalog if catalog is not None else load_catalog(self.models_dir)

    def get(self, model_id: str) -> ModelSpec:
        for spec in self.catalog:
            if spec.model_id == model_id:
                return spec
        return self.catalog[0]

    def path_for(self, spec: ModelSpec) -> Path:
        return self.models_dir / spec.filename

    def part_path_for(self, spec: ModelSpec) -> Path:
        return self.models_dir / (spec.filename + ".part")

    def partial_bytes(self, spec: ModelSpec) -> int:
        try:
            return self.part_path_for(spec).stat().st_size
        except OSError:
            return 0

    def status(self, spec: ModelSpec) -> ModelStatus:
        try:
            if self.path_for(spec).stat().st_size > 0:
                return ModelStatus.PRESENT
        except OSError:
            pass
        return ModelStatus.PARTIAL if self.partial_bytes(spec) > 0 else ModelStatus.MISSING

    def download(
        self,
        spec: ModelSpec,
        *,
        consent: bool,
        progress: Callable[[int, int | None], None] | None = None,
        status: Callable[[str], None] | None = None,
        token: CancelToken | None = None,
        allowed_schemes: tuple[str, ...] = ("https",),
    ) -> Path:
        """Mengunduh model. consent harus True, yaitu hasil persetujuan eksplisit pengguna."""
        result = downloader.download_file(
            spec.url,
            self.path_for(spec),
            consent=consent,
            checksum=spec.checksum,
            progress=progress,
            status=status,
            token=token,
            allowed_schemes=allowed_schemes,
        )
        return result.path

    def remove(self, spec: ModelSpec) -> None:
        """Menghapus berkas model (dan sisa unduhan). Dipakai bila model terbukti rusak."""
        for path in (self.path_for(spec), self.part_path_for(spec)):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Gagal menghapus %s: %s", path, exc)
