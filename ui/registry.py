"""Daftar halaman dan alat. Satu-satunya tempat nama menu dan deskripsi alat didefinisikan."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageInfo:
    page_id: str
    title: str
    icon: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    group: str = "tool"  # home, tool, atau other
    planned: tuple[str, ...] = ()  # fitur yang direncanakan, tampil di halaman Segera Hadir


@dataclass(frozen=True)
class CategoryInfo:
    title: str
    description: str
    tool_ids: tuple[str, ...]


PAGES: tuple[PageInfo, ...] = (
    PageInfo("dashboard", "Dashboard", "dashboard", group="home"),
    PageInfo(
        "qr",
        "QR Code Generator",
        "qr",
        "Buat kode QR untuk tautan, Wi-Fi, kontak, dan lainnya.",
        ("qr", "kode", "barcode", "tautan", "url", "wifi", "whatsapp", "vcard", "email"),
        planned=(
            "Delapan jenis isi: URL, teks, WhatsApp, Wi-Fi, email, telepon, vCard, dan lokasi Google Maps",
            "Pengaturan warna, ukuran, tingkat koreksi kesalahan, batas tepi, dan logo di tengah",
            "Pratinjau langsung serta peringatan bila kode QR berisiko sulit dipindai",
            "Ekspor ke PNG, JPG, SVG, dan PDF",
        ),
    ),
    PageInfo(
        "background",
        "Background Remover",
        "background",
        "Hapus latar belakang gambar dengan AI yang berjalan di komputer Anda.",
        ("latar", "background", "hapus", "transparan", "png", "ai", "potong"),
        planned=(
            "Penghapusan latar belakang dengan model AI yang berjalan di komputer Anda",
            "Model AI diunduh hanya setelah Anda menyetujuinya, dengan indikator progres",
            "Pratinjau sebelum dan sesudah, latar warna solid atau gambar lain",
            "Proses banyak gambar sekaligus dan dapat dibatalkan kapan saja",
        ),
    ),
    PageInfo(
        "resizer",
        "Image Resizer",
        "resizer",
        "Ubah ukuran gambar sesuai kebutuhan media sosial.",
        ("ukuran", "resize", "skala", "instagram", "youtube", "tiktok", "facebook"),
        planned=(
            "Ukuran kustom dengan kunci rasio, atau berdasarkan persentase",
            "Preset ukuran media sosial yang dapat diatur sendiri",
            "Proses banyak gambar, pilihan format keluaran, dan kualitas JPEG",
            "Pratinjau gambar dan pilihan folder keluaran",
        ),
    ),
    PageInfo(
        "converter",
        "Image Converter",
        "converter",
        "Konversi gambar antar format PNG, JPG, WEBP, BMP, TIFF, dan GIF.",
        ("format", "konversi", "convert", "jpg", "jpeg", "webp", "gif", "bmp", "tiff"),
        planned=(
            "Konversi antar PNG, JPG, WEBP, BMP, TIFF, dan GIF",
            "Peringatan jelas bila transparansi atau animasi akan hilang",
            "Konversi satu berkas atau banyak berkas sekaligus",
            "Pengaturan kualitas, pratinjau, dan pilihan folder keluaran",
        ),
    ),
    PageInfo(
        "recent",
        "Proyek Terbaru",
        "clock",
        "Daftar berkas yang baru Anda proses beserta lokasinya.",
        group="other",
        planned=(
            "Daftar berkas hasil proses dari semua alat",
            "Membuka folder hasil dengan satu klik",
            "Pemberitahuan halus bila berkas sudah dipindah atau dihapus",
            "Riwayat disimpan lokal di komputer Anda, tanpa isi gambar",
        ),
    ),
    PageInfo("settings", "Pengaturan", "settings", group="other"),
    PageInfo("about", "Tentang", "info", group="other"),
)

CATEGORIES: tuple[CategoryInfo, ...] = (
    CategoryInfo(
        "Kode dan Tautan",
        "Buat kode QR statis tanpa server eksternal.",
        ("qr",),
    ),
    CategoryInfo(
        "Pengeditan Gambar",
        "Hapus latar belakang, ubah ukuran, dan konversi format gambar.",
        ("background", "resizer", "converter"),
    ),
)


def get_page(page_id: str) -> PageInfo:
    for page in PAGES:
        if page.page_id == page_id:
            return page
    raise KeyError(page_id)


def tool_pages() -> list[PageInfo]:
    return [page for page in PAGES if page.group == "tool"]


def main_pages() -> list[PageInfo]:
    return [page for page in PAGES if page.group in ("home", "tool")]


def other_pages() -> list[PageInfo]:
    return [page for page in PAGES if page.group == "other"]
