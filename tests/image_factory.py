"""Gambar uji sintetis dengan ground truth. BUKAN foto asli: hanya untuk menguji alur dan geometri."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw


def _noise_background(width: int, height: int, low: int, high: int, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    small = rng.integers(low, high, (height // 8 + 1, width // 8 + 1, 3), dtype=np.uint8)
    return Image.fromarray(small).resize((width, height), Image.Resampling.BICUBIC)


class _Canvas:
    """Menggambar bentuk yang sama ke gambar dan mask kebenarannya."""

    def __init__(self, image: Image.Image) -> None:
        self.image = image
        self.mask = Image.new("L", image.size, 0)
        self._d = ImageDraw.Draw(image)
        self._m = ImageDraw.Draw(self.mask)

    def ellipse(self, box, color) -> None:
        self._d.ellipse(box, fill=color)
        self._m.ellipse(box, fill=255)

    def rect(self, box, color, radius: int = 0) -> None:
        if radius:
            self._d.rounded_rectangle(box, radius=radius, fill=color)
            self._m.rounded_rectangle(box, radius=radius, fill=255)
        else:
            self._d.rectangle(box, fill=color)
            self._m.rectangle(box, fill=255)

    def line(self, points, color, width: int) -> None:
        self._d.line(points, fill=color, width=width)
        self._m.line(points, fill=255, width=width)

    def polygon(self, points, color) -> None:
        self._d.polygon(points, fill=color)
        self._m.polygon(points, fill=255)

    def hole(self, box, background) -> None:
        self._d.ellipse(box, fill=background)
        self._m.ellipse(box, fill=0)


def person_like(width: int = 640, height: int = 800) -> tuple[Image.Image, Image.Image]:
    """Siluet orang: kepala, leher, bahu, dan helai rambut tipis. Latar gelap bertekstur."""
    canvas = _Canvas(_noise_background(width, height, 15, 55, seed=1))
    cx = width // 2
    canvas.ellipse((cx - 230, int(height * 0.62), cx + 230, int(height * 1.15)), (210, 215, 235))
    canvas.rect((cx - 45, int(height * 0.38), cx + 45, int(height * 0.66)), (225, 190, 160))
    canvas.ellipse((cx - 95, int(height * 0.14), cx + 95, int(height * 0.44)), (236, 200, 170))
    for index in range(40):
        angle = math.radians(200 + index * 3.5)
        x0, y0 = cx + 70 * math.cos(angle), int(height * 0.18) + 40 * math.sin(angle)
        canvas.line([(x0, y0), (x0 + 70 * math.cos(angle), y0 + 70 * math.sin(angle))], (245, 235, 200), 2)
    return canvas.image, canvas.mask


def product_like(width: int = 800, height: int = 600) -> tuple[Image.Image, Image.Image]:
    """Botol produk dengan label dan tutup, di atas latar gradasi gelap."""
    gradient = np.linspace(25, 70, height, dtype=np.uint8)[:, None, None].repeat(width, 1).repeat(3, 2)
    canvas = _Canvas(Image.fromarray(gradient))
    canvas.rect((width // 2 - 100, 180, width // 2 + 100, 520), (225, 230, 238), radius=40)
    canvas.rect((width // 2 - 40, 95, width // 2 + 40, 185), (225, 230, 238))
    canvas.rect((width // 2 - 50, 60, width // 2 + 50, 98), (245, 200, 60), radius=6)
    canvas.rect((width // 2 - 95, 290, width // 2 + 95, 400), (255, 190, 60))
    return canvas.image, canvas.mask


def complex_detail(width: int = 900, height: int = 700) -> tuple[Image.Image, Image.Image]:
    """Roda gigi berlubang dengan cabang tipis seperti pohon: banyak struktur halus."""
    canvas = _Canvas(_noise_background(width, height, 10, 45, seed=3))
    cx, cy = width // 2, int(height * 0.42)
    teeth = []
    for index in range(24):
        for radius, offset in ((215, 0.0), (215, 0.12), (255, 0.14), (255, 0.26)):
            angle = (index + offset) * 2 * math.pi / 24
            teeth.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    canvas.polygon(teeth, (230, 225, 215))
    canvas.ellipse((cx - 200, cy - 200, cx + 200, cy + 200), (230, 225, 215))
    for angle in range(0, 360, 60):
        px, py = cx + 120 * math.cos(math.radians(angle)), cy + 120 * math.sin(math.radians(angle))
        canvas.hole((px - 38, py - 38, px + 38, py + 38), (28, 28, 28))
    canvas.hole((cx - 30, cy - 30, cx + 30, cy + 30), (28, 28, 28))

    def branch(x, y, angle, length, depth):
        if depth == 0 or length < 6:
            return
        x2, y2 = x + length * math.cos(angle), y - length * math.sin(angle)
        canvas.line([(x, y), (x2, y2)], (235, 235, 225), max(1, depth // 2))
        branch(x2, y2, angle + 0.45, length * 0.72, depth - 1)
        branch(x2, y2, angle - 0.45, length * 0.72, depth - 1)

    branch(cx, height - 5, math.pi / 2, 120, 7)
    return canvas.image, canvas.mask


def iou(alpha: Image.Image, truth: Image.Image, threshold: int = 127) -> float:
    a = np.asarray(alpha.convert("L")) > threshold
    t = np.asarray(truth.convert("L")) > threshold
    union = np.logical_or(a, t).sum()
    return float(np.logical_and(a, t).sum() / union) if union else 1.0
