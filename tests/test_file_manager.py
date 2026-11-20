import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core import file_manager as fm

EXT = {".jpg", ".jpeg", ".png", ".webp"}
FMT = {"JPEG", "PNG", "WEBP"}


class FileManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def make(self, name: str, fmt: str = "PNG", size=(20, 10)) -> Path:
        path = self.tmp / name
        Image.new("RGB", size, (10, 20, 30)).save(path, format=fmt)
        return path

    def test_sanitize_filename(self) -> None:
        self.assertEqual(fm.sanitize_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")
        self.assertEqual(fm.sanitize_filename(""), fm.DEFAULT_STEM)
        self.assertEqual(fm.sanitize_filename("  ..  "), fm.DEFAULT_STEM)
        self.assertEqual(fm.sanitize_filename("NUL"), "_NUL")
        self.assertEqual(fm.sanitize_filename("Foto Liburan Ñandú"), "Foto Liburan Ñandú")
        self.assertLessEqual(len(fm.sanitize_filename("x" * 500)), 120)

    def test_reserve_unique_path_never_overwrites(self) -> None:
        target = self.tmp / "Folder Baru" / "Sub ñ"
        first = fm.reserve_unique_path(target, "hasil", ".png")
        first.write_bytes(b"asli")
        second = fm.reserve_unique_path(target, "hasil", ".png")
        third = fm.reserve_unique_path(target, "hasil", ".png")
        self.assertEqual([first.name, second.name, third.name], ["hasil.png", "hasil (1).png", "hasil (2).png"])
        self.assertEqual(first.read_bytes(), b"asli")

    def test_directory_that_is_a_file(self) -> None:
        blocker = self.tmp / "berkas.txt"
        blocker.write_text("x", encoding="utf-8")
        with self.assertRaises(fm.FileOperationError):
            fm.reserve_unique_path(blocker, "a", ".png")

    def test_discard_file(self) -> None:
        path = self.tmp / "x.bin"
        path.write_bytes(b"1")
        fm.discard_file(path)
        self.assertFalse(path.exists())
        fm.discard_file(path)
        fm.discard_file(None)

    def test_expand_paths(self) -> None:
        folder = self.tmp / "galeri"
        folder.mkdir()
        a = self.make("galeri/a.png")
        b = self.make("galeri/b.JPG", "JPEG")
        (folder / "catatan.txt").write_text("x", encoding="utf-8")
        solo = self.make("solo.png")
        result = fm.expand_paths([folder, solo, a, str(solo)], EXT)
        self.assertEqual([p.name for p in result], ["a.png", "b.JPG", "solo.png"])

    def test_inspect_image_accepts_valid(self) -> None:
        info = fm.inspect_image(self.make("ok.png", size=(30, 20)), EXT, FMT, 10_000)
        self.assertEqual((info.width, info.height, info.format, info.frames), (30, 20, "PNG", 1))

    def test_inspect_image_rejections(self) -> None:
        cases = {
            "bmp": self.make("x.bmp", "BMP"),
            "teks": self.tmp / "palsu.png",
            "hilang": self.tmp / "tidak-ada.png",
            "folder": self.tmp,
        }
        cases["teks"].write_text("ini bukan gambar", encoding="utf-8")
        for label, path in cases.items():
            with self.subTest(label), self.assertRaises(fm.InvalidImageError):
                fm.inspect_image(path, EXT, FMT, 10_000)

    def test_real_format_must_be_allowed_even_with_good_extension(self) -> None:
        disguised = self.make("tipuan.png", "BMP")
        with self.assertRaises(fm.InvalidImageError):
            fm.inspect_image(disguised, EXT, FMT, 10_000)

    def test_renamed_but_allowed_format_is_accepted(self) -> None:
        renamed = self.make("jpeg-dalam-png.png", "JPEG")
        self.assertEqual(fm.inspect_image(renamed, EXT, FMT, 10_000).format, "JPEG")

    def test_pixel_limit(self) -> None:
        with self.assertRaises(fm.InvalidImageError) as ctx:
            fm.inspect_image(self.make("besar.png", size=(200, 100)), EXT, FMT, 1000)
        self.assertIn("terlalu besar", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
