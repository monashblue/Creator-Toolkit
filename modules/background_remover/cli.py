"""Alat evaluasi baris perintah: memproses gambar dengan model yang sudah diunduh dan membuat lembar perbandingan.

Contoh:
    python -m modules.background_remover.cli D:\\Foto\\Uji --model u2net
    python -m modules.background_remover.cli D:\\Foto\\Uji --download

Model hanya diunduh bila Anda memberi opsi --download dan mengetik 'ya' pada konfirmasi.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from app.constants import ensure_directories, get_app_paths
from core.file_manager import expand_paths, reserve_unique_path
from core.tasks import TaskContext, UserMessageError
from modules.background_remover import processor
from modules.background_remover.model_manager import ModelManager, ModelStatus, format_size

CELL = 320


def _thumb(image: Image.Image) -> Image.Image:
    image = image.copy()
    image.thumbnail((CELL, CELL), Image.Resampling.LANCZOS)
    cell = Image.new("RGBA", (CELL, CELL), (255, 255, 255, 255))
    cell.paste(image, ((CELL - image.width) // 2, (CELL - image.height) // 2), image)
    return cell


def build_contact_sheet(rows: list[tuple[Path, Path, float]]) -> Image.Image:
    """Setiap baris: gambar asli, hasil di atas kotak-kotak, dan keterangan."""
    sheet = Image.new("RGB", (CELL * 2 + 20, (CELL + 28) * len(rows)), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (source, output, seconds) in enumerate(rows):
        top = index * (CELL + 28)
        sheet.paste(_thumb(processor.load_preview(source, CELL)).convert("RGB"), (0, top + 24))
        result = processor.composite_on_checkerboard(processor.load_preview(output, CELL))
        sheet.paste(_thumb(result).convert("RGB"), (CELL + 20, top + 24))
        draw.text((4, top + 6), f"{source.name}   ({seconds:.1f} detik)", fill=(30, 30, 30))
    return sheet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluasi Background Remover pada foto Anda sendiri.")
    parser.add_argument("inputs", nargs="+", help="Berkas atau folder gambar (JPG, PNG, WEBP).")
    parser.add_argument("--model", default="u2net", help="ID model pada katalog (bawaan: u2net).")
    parser.add_argument("--output", default=None, help="Folder hasil (bawaan: folder 'hasil-evaluasi' di sebelah gambar pertama).")
    parser.add_argument("--download", action="store_true", help="Izinkan mengunduh model bila belum ada (dengan konfirmasi).")
    parser.add_argument("--max", type=int, default=12, help="Jumlah gambar maksimum pada lembar perbandingan.")
    args = parser.parse_args(argv)

    paths = get_app_paths()
    ensure_directories(paths)
    manager = ModelManager(paths.models_dir)
    spec = manager.get(args.model)

    if manager.status(spec) != ModelStatus.PRESENT:
        size = f"sekitar {spec.approx_size_mb} MB" if spec.approx_size_mb else "ukuran tidak diketahui"
        if not args.download:
            print(f"Model '{spec.display_name}' belum diunduh ({size}). Jalankan lagi dengan --download untuk mengunduhnya.")
            return 2
        print(f"Model: {spec.display_name}\nUkuran: {size}\nSumber: {spec.source_host}\nTujuan: {manager.models_dir}")
        if input("Ketik 'ya' untuk mengunduh: ").strip().lower() != "ya":
            print("Dibatalkan. Tidak ada yang diunduh.")
            return 1
        try:
            manager.download(
                spec, consent=True,
                progress=lambda done, total: print(f"\rMengunduh: {format_size(done)}" + (f" dari {format_size(total)}" if total else ""), end=""),
            )
            print()
        except UserMessageError as exc:
            print(f"\nGagal: {exc}")
            return 1

    files = expand_paths(args.inputs, processor.SUPPORTED_EXTENSIONS)
    if not files:
        print("Tidak ada gambar yang ditemukan.")
        return 1
    first = Path(args.inputs[0])
    output_dir = Path(args.output) if args.output else (first if first.is_dir() else first.parent) / "hasil-evaluasi"

    ctx = TaskContext(on_progress=lambda pct, msg: print(f"[{pct:3d}%] {msg}"))
    try:
        results = processor.run_background_removal(ctx, manager, spec, files, output_dir, processor.BackgroundOptions())
    except UserMessageError as exc:
        print(f"Gagal: {exc}")
        return 1

    ok = [r for r in results if r.status == processor.STATUS_OK]
    for r in results:
        print(f"{'OK   ' if r.status == processor.STATUS_OK else 'GAGAL'} {r.source.name}: " + (f"{r.seconds:.1f} detik" if r.output else r.message))
    if ok:
        sheet_path = reserve_unique_path(output_dir, "perbandingan", ".png")
        build_contact_sheet([(r.source, r.output, r.seconds) for r in ok[: args.max]]).save(sheet_path)
        print(f"\nLembar perbandingan: {sheet_path}\nPeriksa sendiri tepi rambut, bagian tipis, dan objek transparan.")
    return 0 if len(ok) == len(results) else 3


if __name__ == "__main__":
    sys.exit(main())
