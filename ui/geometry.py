"""Perhitungan geometri tampilan perbandingan. Tanpa Qt agar dapat diuji."""

from __future__ import annotations


def fit_rect(src_w: int, src_h: int, dst_w: int, dst_h: int) -> tuple[int, int, int, int]:
    """Menempatkan gambar src di tengah area dst dengan mempertahankan rasio. Mengembalikan (x, y, w, h)."""
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return 0, 0, 0, 0
    scale = min(dst_w / src_w, dst_h / src_h)
    width, height = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    return (dst_w - width) // 2, (dst_h - height) // 2, width, height


def clamp_ratio(ratio: float) -> float:
    return max(0.0, min(1.0, ratio))


def divider_x(rect_x: int, rect_w: int, ratio: float) -> int:
    return rect_x + round(rect_w * clamp_ratio(ratio))


def ratio_from_x(x: float, rect_x: int, rect_w: int) -> float:
    if rect_w <= 0:
        return 0.5
    return clamp_ratio((x - rect_x) / rect_w)
