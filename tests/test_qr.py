import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from modules.qr_generator import exporter, payloads, processor, validator
from modules.qr_generator.processor import QRSettings
from tests.qr_helpers import HAS_DECODER, HAS_QRCODE, decode_pil, make_logo, rasterize_svg

needs_engine = unittest.skipUnless(HAS_QRCODE, "pustaka qrcode belum terpasang")
needs_decoder = unittest.skipUnless(HAS_QRCODE and HAS_DECODER, "qrcode atau OpenCV belum terpasang")

# (jenis, isian, payload yang diharapkan)
SAMPLES = [
    ("url", {"url": "contoh.id/halaman"}, "https://contoh.id/halaman"),
    ("text", {"text": "Halo dunia dari Creator Toolkit"}, "Halo dunia dari Creator Toolkit"),
    (
        "whatsapp",
        {"phone": "+62 812-3456-7890", "message": "Halo, saya mau tanya"},
        "https://wa.me/6281234567890?text=Halo%2C%20saya%20mau%20tanya",
    ),
    (
        "wifi",
        {"ssid": "Kantor;Lantai 2", "security": "WPA", "password": 'kata:sandi,"aman"\\1', "hidden": True},
        'WIFI:T:WPA;S:Kantor\\;Lantai 2;P:kata\\:sandi\\,\\"aman\\"\\\\1;H:true;;',
    ),
    (
        "email",
        {"to": "halo@contoh.id", "subject": "Tanya produk", "body": "Halo\nSaya ingin bertanya"},
        "mailto:halo@contoh.id?subject=Tanya%20produk&body=Halo%0ASaya%20ingin%20bertanya",
    ),
    ("phone", {"number": "+62 21 1234 5678"}, "tel:+622112345678"),
    (
        "vcard",
        {
            "first_name": "Budi", "last_name": "Santoso", "org": "PT Contoh, Tbk", "job_title": "Direktur",
            "phone": "+62 812 3456 7890", "email": "budi@contoh.id", "website": "contoh.id",
            "street": "Jl. Merdeka No. 1", "city": "Jakarta", "region": "DKI Jakarta",
            "postal_code": "10110", "country": "Indonesia",
        },
        "BEGIN:VCARD\r\nVERSION:3.0\r\nN:Santoso;Budi;;;\r\nFN:Budi Santoso\r\nORG:PT Contoh\\, Tbk\r\n"
        "TITLE:Direktur\r\nTEL;TYPE=CELL:+6281234567890\r\nEMAIL:budi@contoh.id\r\nURL:https://contoh.id\r\n"
        "ADR;TYPE=WORK:;;Jl. Merdeka No. 1;Jakarta;DKI Jakarta;10110;Indonesia\r\nEND:VCARD",
    ),
    (
        "maps",
        {"location": "-6.2088, 106.8456"},
        "https://www.google.com/maps/search/?api=1&query=-6.2088%2C106.8456",
    ),
    (
        "maps",
        {"location": "Monumen Nasional, Jakarta"},
        "https://www.google.com/maps/search/?api=1&query=Monumen%20Nasional%2C%20Jakarta",
    ),
    (
        "maps",
        {"location": "https://www.google.com/maps/place/Monas"},
        "https://www.google.com/maps/place/Monas",
    ),
]


def build(type_id, values):
    result = validator.validate(type_id, values)
    assert result.ok, result.errors
    return payloads.build_payload(type_id, result.normalized)


class PayloadTests(unittest.TestCase):
    def test_all_eight_types_are_defined(self) -> None:
        self.assertEqual(
            set(payloads.QR_TYPE_IDS),
            {"url", "text", "whatsapp", "wifi", "email", "phone", "vcard", "maps"},
        )
        self.assertEqual(len(payloads.QR_TYPES), 8)

    def test_payload_strings(self) -> None:
        for type_id, values, expected in SAMPLES:
            with self.subTest(type=type_id, values=values):
                self.assertEqual(build(type_id, values), expected)

    def test_wifi_without_password(self) -> None:
        result = validator.validate("wifi", {"ssid": "Tamu", "security": "nopass", "password": "abc"})
        self.assertTrue(result.ok)
        self.assertEqual(payloads.build_payload("wifi", result.normalized), "WIFI:T:nopass;S:Tamu;;")
        self.assertTrue(result.warnings)


class ValidationTests(unittest.TestCase):
    CASES = [
        ("url", {"url": ""}, "url"),
        ("url", {"url": "bukan url"}, "url"),
        ("url", {"url": "https://abc"}, "url"),
        ("url", {"url": "javascript:alert(1)"}, "url"),
        ("url", {"url": "ftp://contoh.id"}, "url"),
        ("text", {"text": "   "}, "text"),
        ("text", {"text": "a" * 3000}, "text"),
        ("whatsapp", {"phone": ""}, "phone"),
        ("whatsapp", {"phone": "0812345678"}, "phone"),
        ("whatsapp", {"phone": "62abc12345"}, "phone"),
        ("whatsapp", {"phone": "6212"}, "phone"),
        ("wifi", {"ssid": "", "security": "nopass"}, "ssid"),
        ("wifi", {"ssid": "x" * 33, "security": "nopass"}, "ssid"),
        ("wifi", {"ssid": "Rumah", "security": "WPA", "password": "pendek"}, "password"),
        ("wifi", {"ssid": "Rumah", "security": "WPA", "password": ""}, "password"),
        ("wifi", {"ssid": "Rumah", "security": "WEP", "password": "abcd"}, "password"),
        ("email", {"to": ""}, "to"),
        ("email", {"to": "tanpa-at.id"}, "to"),
        ("email", {"to": "a b@contoh.id"}, "to"),
        ("phone", {"number": "abc"}, "number"),
        ("phone", {"number": "123"}, "number"),
        ("vcard", {"first_name": "", "last_name": ""}, "first_name"),
        ("vcard", {"first_name": "Budi", "email": "salah"}, "email"),
        ("vcard", {"first_name": "Budi", "phone": "xyz"}, "phone"),
        ("vcard", {"first_name": "Budi", "website": "bukan url"}, "website"),
        ("maps", {"location": ""}, "location"),
        ("maps", {"location": "95.0, 106.0"}, "location"),
        ("maps", {"location": "-6.0, 200.0"}, "location"),
        ("maps", {"location": "https://contoh.id/peta"}, "location"),
    ]

    def test_invalid_inputs_report_the_right_field(self) -> None:
        for type_id, values, field_key in self.CASES:
            with self.subTest(type=type_id, values=values):
                result = validator.validate(type_id, values)
                self.assertFalse(result.ok)
                self.assertIn(field_key, result.errors)
                self.assertTrue(result.errors[field_key])

    def test_url_normalization_adds_https(self) -> None:
        result = validator.validate("url", {"url": "contoh.id"})
        self.assertEqual(result.normalized["url"], "https://contoh.id")
        self.assertTrue(result.warnings)

    def test_unknown_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            validator.validate("tidak-ada", {})


class SettingsTests(unittest.TestCase):
    def test_equal_colors_are_an_error(self) -> None:
        errors, _ = processor.validate_settings(QRSettings(foreground="#112233", background="#112233"))
        self.assertIn("foreground", errors)

    def test_invalid_hex_and_ranges(self) -> None:
        errors, _ = processor.validate_settings(
            QRSettings(foreground="merah", background="#FFF", size_px=10, border=99, error_correction="Z")
        )
        for key in ("foreground", "background", "size", "border", "error_correction"):
            self.assertIn(key, errors)

    def test_low_contrast_and_inverted_warnings(self) -> None:
        _, warnings = processor.validate_settings(QRSettings(foreground="#777777", background="#888888"))
        self.assertTrue(any("Kontras" in w for w in warnings))
        _, warnings = processor.validate_settings(QRSettings(foreground="#FFFFFF", background="#000000"))
        self.assertTrue(any("terbalik" in w for w in warnings))

    def test_good_contrast_has_no_warning(self) -> None:
        errors, warnings = processor.validate_settings(QRSettings(foreground="#1A237E", background="#FFFFFF"))
        self.assertEqual((errors, warnings), ({}, []))

    def test_small_border_warning(self) -> None:
        _, warnings = processor.validate_settings(QRSettings(border=1))
        self.assertTrue(any("Zona tenang" in w for w in warnings))

    def test_logo_requires_ec_m_or_higher(self) -> None:
        errors, _ = processor.validate_settings(QRSettings(error_correction="L", logo_path="x.png"))
        self.assertIn("logo", errors)

    def test_logo_size_never_exceeds_limit(self) -> None:
        for ec in ("M", "Q", "H"):
            for modules in (21, 25, 33, 45, 57, 89):
                for ratio in (0.05, 0.2, 0.5, 1.0):
                    count = processor.logo_modules_for(modules, ratio, ec)
                    self.assertLessEqual(count, processor.MAX_LOGO_RATIO[ec] * modules)
                    if count:
                        self.assertEqual((modules - count) % 2, 0)
        self.assertEqual(processor.logo_modules_for(33, 0.5, "L"), 0)


@needs_decoder
class DecodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def generate(self, type_id, values, **settings):
        return processor.generate_qr(type_id, values, QRSettings(**settings))

    def test_every_type_decodes_to_its_payload(self) -> None:
        for type_id, values, expected in SAMPLES:
            with self.subTest(type=type_id, values=values):
                result = self.generate(type_id, values)
                self.assertEqual(result.payload, expected)
                self.assertEqual(decode_pil(result.image), expected)

    def test_every_error_correction_level_decodes(self) -> None:
        for ec in processor.EC_LEVELS:
            with self.subTest(ec=ec):
                result = self.generate("text", {"text": "Uji tingkat koreksi " + ec}, error_correction=ec)
                self.assertEqual(decode_pil(result.image), result.payload)

    def test_custom_colors_decode(self) -> None:
        result = self.generate("url", {"url": "https://contoh.id"}, foreground="#1A237E", background="#FFF8E1")
        self.assertEqual(decode_pil(result.image), "https://contoh.id")
        self.assertEqual(result.warnings, [])

    def test_sizes_and_borders(self) -> None:
        for size in (128, 300, 1000, 2048):
            for border in (0, 4, 10):
                with self.subTest(size=size, border=border):
                    result = self.generate("text", {"text": "ukuran"}, size_px=size, border=border)
                    total = result.modules + 2 * border
                    self.assertEqual(result.size_px, result.module_px * total)
                    self.assertLessEqual(abs(result.size_px - size), total)
                    if border >= 4 and result.module_px >= 3:
                        self.assertEqual(decode_pil(result.image), "ukuran")

    def test_small_modules_warn(self) -> None:
        result = self.generate("text", {"text": "x" * 200}, size_px=128)
        self.assertTrue(any("piksel" in w for w in result.warnings))

    def test_logo_at_maximum_size_stays_scannable(self) -> None:
        logo_path = self.tmp / "logo.png"
        make_logo(logo_path)
        samples = {
            "pendek": "https://contoh.id/halaman",
            "panjang": ("Teks yang lebih panjang agar kode QR lebih besar. " * 3).strip(),
        }
        for ec in ("M", "Q", "H"):
            for label, text in samples.items():
                with self.subTest(ec=ec, isi=label):
                    result = self.generate(
                        "text", {"text": text}, error_correction=ec, logo_path=str(logo_path),
                        logo_ratio=1.0, size_px=800,
                    )
                    self.assertIsNotNone(result.logo)
                    self.assertLessEqual(result.logo.modules, processor.MAX_LOGO_RATIO[ec] * result.modules)
                    self.assertEqual(decode_pil(result.image), text)

    def test_logo_with_ec_l_is_rejected(self) -> None:
        logo_path = self.tmp / "logo.png"
        make_logo(logo_path)
        with self.assertRaises(processor.QRValidationError) as ctx:
            self.generate("text", {"text": "x"}, error_correction="L", logo_path=str(logo_path))
        self.assertIn("logo", ctx.exception.setting_errors)

    def test_bad_logo_files(self) -> None:
        with self.assertRaises(processor.QRGenerationError):
            self.generate("text", {"text": "x"}, logo_path=str(self.tmp / "tidak-ada.png"))
        fake = self.tmp / "palsu.png"
        fake.write_text("ini bukan gambar", encoding="utf-8")
        with self.assertRaises(processor.QRGenerationError):
            self.generate("text", {"text": "x"}, logo_path=str(fake))

    def test_overflow_gives_friendly_error(self) -> None:
        with self.assertRaises(processor.QRGenerationError) as ctx:
            self.generate("text", {"text": "a" * 2800}, error_correction="H")
        self.assertIn("terlalu panjang", str(ctx.exception))

    def test_invalid_input_raises_validation_error(self) -> None:
        with self.assertRaises(processor.QRValidationError) as ctx:
            self.generate("url", {"url": "bukan url"})
        self.assertIn("url", ctx.exception.field_errors)

    def test_exports_decode_in_every_format(self) -> None:
        out = self.tmp / "Hasil QR" / "Folder ñandú"
        for type_id, values, expected in SAMPLES:
            result = self.generate(type_id, values, foreground="#0D47A1", size_px=600)
            for fmt in ("PNG", "JPG", "SVG"):
                with self.subTest(type=type_id, values=values, format=fmt):
                    exported = exporter.export_qr(result, out, f"qr {type_id}", fmt)
                    self.assertTrue(exported.path.is_file())
                    self.assertEqual(exported.path.suffix, exporter.FORMATS[fmt])
                    if fmt == "SVG":
                        from PIL import Image
                        image = rasterize_svg(exported.path.read_text(encoding="utf-8"))
                    else:
                        from PIL import Image
                        with Image.open(exported.path) as handle:
                            image = handle.copy()
                    self.assertEqual(decode_pil(image), expected)

    def test_svg_with_logo_decodes(self) -> None:
        logo_path = self.tmp / "logo.png"
        make_logo(logo_path)
        text = ("Teks yang lebih panjang agar kode QR lebih besar. " * 3).strip()
        result = self.generate("text", {"text": text}, error_correction="Q", logo_path=str(logo_path), size_px=800)
        exported = exporter.export_qr(result, self.tmp, "dengan logo", "SVG")
        svg = exported.path.read_text(encoding="utf-8")
        self.assertIn('id="logo"', svg)
        self.assertEqual(decode_pil(rasterize_svg(svg)), text)

    @unittest.skipUnless(shutil.which("pdftoppm"), "pdftoppm tidak tersedia")
    def test_pdf_export_decodes(self) -> None:
        logo_path = self.tmp / "logo.png"
        make_logo(logo_path)
        for logo in (None, str(logo_path)):
            with self.subTest(logo=bool(logo)):
                result = self.generate(
                    "wifi", {"ssid": "Kantor", "security": "WPA", "password": "rahasia123"},
                    error_correction="Q" if logo else "M", logo_path=logo, size_px=600,
                )
                exported = exporter.export_qr(result, self.tmp, "kode pdf", "PDF")
                header = exported.path.read_bytes()[:5]
                self.assertEqual(header, b"%PDF-")
                prefix = self.tmp / f"render{bool(logo)}"
                subprocess.run(
                    ["pdftoppm", "-r", "300", "-png", str(exported.path), str(prefix)],
                    check=True, capture_output=True,
                )
                rendered = next(self.tmp.glob(f"{prefix.name}*.png"))
                from PIL import Image
                with Image.open(rendered) as handle:
                    self.assertEqual(decode_pil(handle.copy()), result.payload)

    def test_export_never_overwrites(self) -> None:
        result = self.generate("text", {"text": "satu"})
        first = exporter.export_qr(result, self.tmp, "kode", "PNG")
        original = first.path.read_bytes()
        other = self.generate("text", {"text": "dua"})
        second = exporter.export_qr(other, self.tmp, "kode", "PNG")
        third = exporter.export_qr(other, self.tmp, "kode", "PNG")
        self.assertEqual(first.path.name, "kode.png")
        self.assertEqual(second.path.name, "kode (1).png")
        self.assertEqual(third.path.name, "kode (2).png")
        self.assertEqual(first.path.read_bytes(), original)


@needs_engine
class PreviewRenderTests(unittest.TestCase):
    TEXT = {"text": "uji pratinjau"}

    def test_preview_is_small_but_reports_final_size(self) -> None:
        settings = QRSettings(size_px=4096)
        full = processor.generate_qr("text", self.TEXT, settings)
        preview = processor.generate_qr("text", self.TEXT, settings, render_size_px=300)
        self.assertTrue(preview.preview_only)
        self.assertFalse(full.preview_only)
        self.assertLess(preview.size_px, 400)
        self.assertGreater(full.size_px, 4000)
        self.assertEqual(preview.final_size_px, full.size_px)
        self.assertEqual(preview.matrix, full.matrix)

    def test_cap_larger_than_size_changes_nothing(self) -> None:
        result = processor.generate_qr("text", self.TEXT, QRSettings(size_px=512), render_size_px=2000)
        self.assertFalse(result.preview_only)
        self.assertEqual(result.final_size_px, result.size_px)

    def test_no_false_module_warning_in_preview(self) -> None:
        big = {"text": "isi panjang " * 125}
        settings = QRSettings(size_px=4096)
        preview = processor.generate_qr("text", big, settings, render_size_px=200)
        self.assertFalse(any("piksel" in w for w in preview.warnings))
        tiny = processor.generate_qr("text", big, QRSettings(size_px=128), render_size_px=2000)
        self.assertTrue(any("piksel" in w for w in tiny.warnings))

    def test_preview_cannot_be_exported(self) -> None:
        preview = processor.generate_qr("text", self.TEXT, QRSettings(size_px=2048), render_size_px=200)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(exporter.ExportError):
                exporter.export_qr(preview, tmp, "kode", "PNG")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_matrix_is_cached_per_payload_and_level(self) -> None:
        first = processor.create_matrix("cache uji", "M")
        self.assertIs(first, processor.create_matrix("cache uji", "M"))
        self.assertIsNot(first, processor.create_matrix("cache uji", "H"))
        self.assertIsNot(first, processor.create_matrix("cache uji lain", "M"))


class ExporterTests(unittest.TestCase):
    def test_sanitize_filename(self) -> None:
        self.assertEqual(exporter.sanitize_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")
        self.assertEqual(exporter.sanitize_filename(""), exporter.DEFAULT_STEM)
        self.assertEqual(exporter.sanitize_filename("  ..  "), exporter.DEFAULT_STEM)
        self.assertEqual(exporter.sanitize_filename("CON"), "_CON")
        self.assertEqual(exporter.sanitize_filename("Kode Pelanggan Ñandú"), "Kode Pelanggan Ñandú")
        self.assertLessEqual(len(exporter.sanitize_filename("x" * 500)), 120)

    def test_reserve_unique_path_creates_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Folder Baru" / "Sub Folder"
            path = exporter.reserve_unique_path(target, "kode", ".png")
            self.assertTrue(path.exists())
            again = exporter.reserve_unique_path(target, "kode", ".png")
            self.assertNotEqual(path, again)

    def test_directory_that_is_a_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "berkas.txt"
            blocker.write_text("x", encoding="utf-8")
            with self.assertRaises(exporter.ExportError):
                exporter.reserve_unique_path(blocker, "kode", ".png")

    @needs_engine
    def test_unknown_format_rejected(self) -> None:
        result = processor.generate_qr("text", {"text": "x"}, QRSettings())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(exporter.ExportError):
                exporter.export_qr(result, tmp, "kode", "GIF")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    @needs_engine
    def test_jpg_and_pdf_warn(self) -> None:
        result = processor.generate_qr("text", {"text": "x"}, QRSettings())
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(exporter.export_qr(result, tmp, "a", "JPG").warnings)
            self.assertTrue(exporter.export_qr(result, tmp, "b", "PDF").warnings)
            self.assertFalse(exporter.export_qr(result, tmp, "c", "PNG").warnings)


if __name__ == "__main__":
    unittest.main()
