"""Pembantu pengujian QR: decoder nyata (OpenCV) dan perender SVG sederhana."""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

try:
    import cv2
    import numpy as np

    HAS_DECODER = True
except ImportError:  # pragma: no cover
    HAS_DECODER = False

try:
    import qrcode  # noqa: F401

    HAS_QRCODE = True
except ImportError:  # pragma: no cover
    HAS_QRCODE = False


def decode_pil(image: Image.Image) -> str | None:
    """Membaca QR dari gambar PIL dengan decoder OpenCV. Mengembalikan None bila gagal."""
    gray = np.array(image.convert("L"))
    height, width = gray.shape
    longest = max(height, width)
    if longest < 600:
        scale = 600 // longest
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    elif longest > 1000:
        # Detektor OpenCV gagal pada gambar yang sangat besar. Pemindai asli bekerja dari foto kamera.
        gray = cv2.resize(gray, None, fx=800 / longest, fy=800 / longest, interpolation=cv2.INTER_AREA)
    gray = cv2.copyMakeBorder(gray, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    for detector in detectors:
        value, _points, _ = detector.detectAndDecode(gray)
        if value:
            return value
    return None


def rasterize_svg(svg_text: str, scale: int = 10) -> Image.Image:
    """Merender SVG buatan exporter menjadi gambar, termasuk plat dan logo."""
    ns = "{http://www.w3.org/2000/svg}"
    xlink = "{http://www.w3.org/1999/xlink}"
    root = ET.fromstring(svg_text.encode("utf-8"))
    total = float(root.get("viewBox").split()[2])
    background = root.find(f"{ns}rect").get("fill")
    image = Image.new("RGB", (round(total * scale),) * 2, background)
    draw = ImageDraw.Draw(image)

    path = root.find(f"{ns}path")
    foreground = path.get("fill")
    for match in re.finditer(r"M(\d+) (\d+)h(\d+)v1h-\d+z", path.get("d")):
        x, y, w = (int(v) for v in match.groups())
        draw.rectangle([x * scale, y * scale, (x + w) * scale - 1, (y + 1) * scale - 1], fill=foreground)

    plate = root.find(f".//{ns}rect[@id='logo-plate']")
    if plate is not None:
        x, y, w, h = (float(plate.get(k)) * scale for k in ("x", "y", "width", "height"))
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=plate.get("fill"))
        logo = root.find(f".//{ns}image[@id='logo']")
        href = logo.get(f"{xlink}href")
        data = base64.b64decode(href.split(",", 1)[1])
        logo_img = Image.open(io.BytesIO(data)).convert("RGBA")
        lx, ly, lw, lh = (float(logo.get(k)) * scale for k in ("x", "y", "width", "height"))
        logo_img = logo_img.resize((max(1, round(lw)), max(1, round(lh))))
        image.paste(logo_img, (round(lx), round(ly)), logo_img)
    return image


def make_logo(path, size: int = 240) -> None:
    """Membuat logo uji berwarna: lingkaran merah dengan persegi biru."""
    logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(220, 40, 40, 255))
    draw.rectangle([size // 3, size // 3, 2 * size // 3, 2 * size // 3], fill=(30, 60, 200, 255))
    logo.save(path)
