import hashlib
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from core.tasks import OperationCancelled, TaskContext
from modules.background_remover import model_manager as mm
from modules.background_remover import processor as pr
from modules.background_remover.errors import (
    InsufficientMemoryError,
    ModelInvalidError,
    ModelNotAvailableError,
    ProcessingError,
    UnsupportedImageError,
)
from tests import image_factory as factory
from tests.onnx_builder import build_saliency_model

FAKE = mm.ModelSpec("fake", "Model uji", "fake.onnx", "https://example.invalid/fake.onnx", approx_size_mb=1)


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        pr.clear_session_cache()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(pr.clear_session_cache)
        self.tmp = Path(self._tmp.name)
        self.models_dir = self.tmp / "models"
        build_saliency_model(self.models_dir / "fake.onnx")
        self.manager = mm.ModelManager(self.models_dir, [FAKE])
        self.out = self.tmp / "Hasil Latar ñ"

    def save(self, name: str, image: Image.Image, fmt: str = "PNG") -> Path:
        path = self.tmp / "input" / name
        path.parent.mkdir(exist_ok=True)
        image.save(path, format=fmt)
        return path

    def run_batch(self, files, options=None, ctx=None):
        ctx = ctx or TaskContext()
        return pr.run_background_removal(ctx, self.manager, FAKE, files, self.out, options or pr.BackgroundOptions())


class CatalogTests(BaseCase):
    def test_default_catalog_is_https_and_unverified_checksums_are_empty(self) -> None:
        ids = [spec.model_id for spec in mm.DEFAULT_CATALOG]
        self.assertEqual(ids[0], mm.DEFAULT_MODEL_ID)
        self.assertEqual(len(ids), len(set(ids)))
        for spec in mm.DEFAULT_CATALOG:
            self.assertTrue(spec.url.startswith("https://"), spec.model_id)
            self.assertTrue(spec.filename.endswith(".onnx"))
            self.assertIsNone(spec.checksum, "checksum hanya boleh diisi setelah diverifikasi dari sumber resmi")
            self.assertIsNotNone(spec.approx_size_mb)

    def test_custom_catalog_adds_and_skips_invalid_entries(self) -> None:
        good = {"model_id": "baru", "display_name": "Model Baru", "filename": "baru.onnx",
                "url": "https://contoh.id/baru.onnx", "input_size": 512, "approx_size_mb": 20,
                "checksum": "sha256:" + "a" * 64}
        bad = [
            {**good, "model_id": "b1", "filename": "../jahat.onnx"},
            {**good, "model_id": "b2", "url": "http://contoh.id/x.onnx"},
            {**good, "model_id": "b3", "input_size": 5},
            {**good, "model_id": "b4", "checksum": "bukan-checksum"},
            {**good, "model_id": "b5", "std": [0, 1, 1]},
            {"model_id": "b6"},
        ]
        (self.models_dir / "catalog.json").write_text(json.dumps({"models": [good, *bad]}), encoding="utf-8")
        catalog = {s.model_id: s for s in mm.load_catalog(self.models_dir)}
        self.assertIn("baru", catalog)
        self.assertEqual(catalog["baru"].input_size, 512)
        for bad_id in ("b1", "b2", "b3", "b4", "b5", "b6"):
            self.assertNotIn(bad_id, catalog)
        self.assertIn("u2net", catalog)

    def test_broken_catalog_file_falls_back_to_default(self) -> None:
        (self.models_dir / "catalog.json").write_text("{ rusak", encoding="utf-8")
        self.assertEqual(len(mm.load_catalog(self.models_dir)), len(mm.DEFAULT_CATALOG))

    def test_status_transitions(self) -> None:
        empty = mm.ModelManager(self.tmp / "kosong", [FAKE])
        self.assertEqual(empty.status(FAKE), mm.ModelStatus.MISSING)
        (self.tmp / "kosong").mkdir()
        empty.part_path_for(FAKE).write_bytes(b"1234")
        self.assertEqual(empty.status(FAKE), mm.ModelStatus.PARTIAL)
        self.assertEqual(empty.partial_bytes(FAKE), 4)
        empty.path_for(FAKE).write_bytes(b"x")
        self.assertEqual(empty.status(FAKE), mm.ModelStatus.PRESENT)
        empty.remove(FAKE)
        self.assertEqual(empty.status(FAKE), mm.ModelStatus.MISSING)

    def test_format_size(self) -> None:
        self.assertEqual(mm.format_size(176 * 1024 * 1024), "176 MB")
        self.assertEqual(mm.format_size(4.6 * 1024 * 1024), "4,6 MB")

    def test_manager_download_needs_consent(self) -> None:
        with self.assertRaises(Exception) as ctx:
            self.manager.download(FAKE, consent=False)
        self.assertIn("persetujuan", str(ctx.exception))


class SessionTests(BaseCase):
    def test_session_loads_and_predicts_non_square_masks(self) -> None:
        session = pr.get_session(FAKE, self.manager.path_for(FAKE))
        self.assertEqual(session.size, (320, 320))
        for size in ((640, 800), (800, 600), (50, 33), (1, 1)):
            mask = session.predict_mask(Image.new("RGB", size, (200, 200, 200)))
            self.assertEqual((mask.size, mask.mode), (size, "L"))

    def test_static_input_size_is_taken_from_model(self) -> None:
        path = build_saliency_model(self.tmp / "m256.onnx", size=256)
        spec = mm.ModelSpec("m256", "x", "m256.onnx", "https://x.invalid/m.onnx", input_size=320)
        session = pr.SegmentationSession(spec, path)
        self.assertEqual(session.size, (256, 256))
        self.assertEqual(session.predict_mask(Image.new("RGB", (100, 60))).size, (100, 60))

    def test_single_output_model_works(self) -> None:
        path = build_saliency_model(self.tmp / "satu.onnx", outputs=1)
        session = pr.SegmentationSession(FAKE, path)
        self.assertEqual(session.predict_mask(Image.new("RGB", (40, 40), (250, 250, 250))).size, (40, 40))

    def test_invalid_model_files(self) -> None:
        junk = self.tmp / "junk.onnx"
        junk.write_text("ini bukan model onnx", encoding="utf-8")
        truncated = self.tmp / "terpotong.onnx"
        truncated.write_bytes((self.models_dir / "fake.onnx").read_bytes()[:40])
        for path in (junk, truncated):
            with self.subTest(path.name), self.assertRaises(ModelInvalidError):
                pr.SegmentationSession(FAKE, path)

    def test_wrong_input_rank_is_rejected(self) -> None:
        path = build_saliency_model(self.tmp / "rank3.onnx", rank=3)
        with self.assertRaises((ModelInvalidError,)):
            pr.SegmentationSession(FAKE, path)

    def test_missing_model(self) -> None:
        with self.assertRaises(ModelNotAvailableError):
            pr.SegmentationSession(FAKE, self.tmp / "tidak-ada.onnx")
        with self.assertRaises(ModelNotAvailableError):
            pr.get_session(FAKE, self.tmp / "tidak-ada.onnx")

    def test_session_cache_reuses_and_invalidates(self) -> None:
        path = self.manager.path_for(FAKE)
        first = pr.get_session(FAKE, path)
        self.assertIs(first, pr.get_session(FAKE, path))
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))  # mtime berubah -> kunci cache berubah
        self.assertIsNot(first, pr.get_session(FAKE, path))

    def test_memory_errors_are_classified(self) -> None:
        self.assertTrue(pr._is_memory_problem(MemoryError()))
        self.assertTrue(pr._is_memory_problem(RuntimeError("std::bad_alloc")))
        self.assertTrue(pr._is_memory_problem(RuntimeError("Failed to allocate memory for ...")))
        self.assertFalse(pr._is_memory_problem(RuntimeError("hal lain")))
        session = pr.get_session(FAKE, self.manager.path_for(FAKE))
        broken = mock.Mock()
        broken.run.side_effect = MemoryError()
        with mock.patch.object(session, "_session", broken):
            with self.assertRaises(InsufficientMemoryError):
                session.predict_mask(Image.new("RGB", (10, 10)))
        broken.run.side_effect = RuntimeError("kegagalan internal")
        with mock.patch.object(session, "_session", broken):
            with self.assertRaises(ProcessingError):
                session.predict_mask(Image.new("RGB", (10, 10)))

    def test_non_finite_output_is_rejected(self) -> None:
        session = pr.get_session(FAKE, self.manager.path_for(FAKE))
        broken = mock.Mock()
        broken.run.return_value = [np.full((1, 1, 320, 320), np.nan, dtype=np.float32)]
        with mock.patch.object(session, "_session", broken):
            with self.assertRaises(ProcessingError):
                session.predict_mask(Image.new("RGB", (10, 10)))


class ImageLoadingTests(BaseCase):
    def test_modes_are_converted_to_rgb(self) -> None:
        base = Image.new("RGB", (30, 20), (200, 100, 50))
        cases = {
            "L": base.convert("L"),
            "P": base.convert("P"),
            "RGBA": base.convert("RGBA"),
            "LA": base.convert("LA"),
        }
        for mode, image in cases.items():
            with self.subTest(mode):
                rgb, _ = pr.load_rgb(self.save(f"{mode}.png", image))
                self.assertEqual((rgb.mode, rgb.size), ("RGB", (30, 20)))
        cmyk = self.save("cmyk.jpg", base.convert("CMYK"), "JPEG")
        self.assertEqual(pr.load_rgb(cmyk)[0].mode, "RGB")

    def test_sixteen_bit_png(self) -> None:
        array = np.linspace(0, 65535, 40 * 30, dtype=np.uint16).reshape(30, 40)
        path = self.tmp / "input" / "abu16.png"
        path.parent.mkdir()
        Image.fromarray(array).save(path)
        rgb, _ = pr.load_rgb(path)
        values = np.asarray(rgb)
        self.assertEqual(rgb.mode, "RGB")
        self.assertGreater(values.max(), 240)
        self.assertLess(values.min(), 15)

    def test_alpha_input_is_flattened_with_warning(self) -> None:
        image = Image.new("RGBA", (10, 10), (255, 0, 0, 0))
        rgb, warnings = pr.load_rgb(self.save("transparan.png", image))
        self.assertEqual(rgb.getpixel((0, 0)), (255, 255, 255))
        self.assertTrue(any("Transparansi" in w for w in warnings))

    def test_exif_orientation_is_applied(self) -> None:
        image = Image.new("RGB", (60, 30), (10, 200, 10))
        exif = Image.Exif()
        exif[0x0112] = 6  # putar 90 derajat
        path = self.tmp / "input" / "miring.jpg"
        path.parent.mkdir()
        image.save(path, format="JPEG", exif=exif)
        self.assertEqual(pr.load_rgb(path)[0].size, (30, 60))

    def test_all_exif_orientations_match_the_reference_implementation(self) -> None:
        from PIL import ImageOps

        source = Image.new("RGB", (60, 30))
        source.putdata([(x * 4 % 256, y * 8 % 256, (x + y) % 256) for y in range(30) for x in range(60)])
        for orientation in range(1, 9):
            with self.subTest(orientation=orientation):
                exif = Image.Exif()
                exif[0x0112] = orientation
                path = self.tmp / "input" / f"o{orientation}.png"
                path.parent.mkdir(exist_ok=True)
                source.save(path, exif=exif)
                with Image.open(path) as handle:
                    reference = ImageOps.exif_transpose(handle).convert("RGB")
                rgb, _ = pr.load_rgb(path)
                self.assertEqual(rgb.size, reference.size)
                self.assertEqual(rgb.tobytes(), reference.tobytes())

    def test_rgb_input_is_not_copied_and_stays_valid_after_file_closes(self) -> None:
        path = self.save("rgb.png", Image.new("RGB", (30, 20), (9, 8, 7)))
        rgb, warnings = pr.load_rgb(path)
        self.assertEqual((rgb.mode, warnings), ("RGB", []))
        self.assertEqual(rgb.getpixel((3, 3)), (9, 8, 7))  # berkas sudah ditutup, piksel tetap terbaca
        path.unlink()  # di Windows, ini gagal bila handle berkas masih terbuka
        self.assertFalse(path.exists())

    def test_animated_webp_warns(self) -> None:
        frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        path = self.tmp / "input" / "anim.webp"
        path.parent.mkdir()
        try:
            frames[0].save(path, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
        except (OSError, ValueError, KeyError):
            self.skipTest("WEBP animasi tidak didukung build Pillow ini")
        self.assertTrue(any("beranimasi" in w for w in pr.load_rgb(path)[1]))

    def test_unsupported_and_corrupt_inputs(self) -> None:
        bmp = self.save("x.bmp", Image.new("RGB", (10, 10)), "BMP")
        gif = self.save("x.gif", Image.new("RGB", (10, 10)), "GIF")
        fake = self.tmp / "input" / "palsu.png"
        fake.write_text("bukan gambar", encoding="utf-8")
        for path in (bmp, gif, fake, self.tmp / "input" / "hilang.png"):
            with self.subTest(path.name), self.assertRaises(Exception) as ctx:
                pr.load_rgb(path)
            self.assertTrue(str(ctx.exception))

    def test_truncated_jpeg_is_reported(self) -> None:
        good = self.save("ok.jpg", factory.product_like()[0], "JPEG")
        broken = self.tmp / "input" / "terpotong.jpg"
        broken.write_bytes(good.read_bytes()[: good.stat().st_size // 2])
        with self.assertRaises((UnsupportedImageError, Exception)) as ctx:
            pr.load_rgb(broken)
        self.assertTrue(str(ctx.exception))

    def test_pixel_limit_blocks_huge_images(self) -> None:
        path = self.save("besar.png", Image.new("RGB", (300, 200)))
        with mock.patch.object(pr, "MAX_PIXELS", 1000):
            with self.assertRaises(Exception) as ctx:
                pr.load_rgb(path)
        self.assertIn("terlalu besar", str(ctx.exception))


class RemovalQualityPipelineTests(BaseCase):
    """Menguji geometri dan alpha pada gambar sintetis. Ini BUKAN uji kualitas model AI."""

    def test_alpha_matches_truth_for_synthetic_scenes(self) -> None:
        session = pr.get_session(FAKE, self.manager.path_for(FAKE))
        for name, minimum in (("person_like", 0.85), ("product_like", 0.9)):
            image, truth = getattr(factory, name)()
            with self.subTest(name):
                rgba = pr.remove_background(image, session)
                self.assertEqual((rgba.mode, rgba.size), ("RGBA", image.size))
                self.assertGreaterEqual(factory.iou(rgba.getchannel("A"), truth), minimum)

    def test_thin_structures_lose_detail_at_model_resolution(self) -> None:
        image, truth = factory.complex_detail()
        session = pr.get_session(FAKE, self.manager.path_for(FAKE))
        score = factory.iou(pr.remove_background(image, session).getchannel("A"), truth)
        self.assertGreater(score, 0.5)
        self.assertLess(score, 0.99)  # struktur tipis tidak sempurna karena inferensi 320 px

    def test_rgb_values_are_preserved(self) -> None:
        image, _ = factory.product_like()
        rgba = pr.remove_background(image, pr.get_session(FAKE, self.manager.path_for(FAKE)))
        np.testing.assert_array_equal(np.asarray(rgba.convert("RGB")), np.asarray(image))


class BatchTests(BaseCase):
    def make_set(self):
        return {
            "orang": self.save("orang.jpg", factory.person_like()[0], "JPEG"),
            "produk": self.save("produk saya ñ.png", factory.product_like()[0]),
            "detail": self.save("detail.webp", factory.complex_detail()[0], "WEBP"),
        }

    def test_batch_outputs_have_alpha_and_originals_are_untouched(self) -> None:
        files = self.make_set()
        corrupt = self.tmp / "input" / "rusak.png"
        corrupt.write_text("bukan gambar", encoding="utf-8")
        bmp = self.save("tidak-didukung.bmp", Image.new("RGB", (10, 10)), "BMP")
        before = {p: sha(p) for p in [*files.values(), corrupt, bmp]}

        items, progress = [], []
        ctx = TaskContext(on_progress=lambda p, m: progress.append(p), on_item=items.append)
        results = self.run_batch([*files.values(), corrupt, bmp], ctx=ctx)

        self.assertEqual([r.status for r in results], ["ok", "ok", "ok", "failed", "failed"])
        self.assertEqual(len(items), 5)
        for result in results[3:]:
            self.assertTrue(result.message)
            self.assertIsNone(result.output)
        for name, path in files.items():
            result = next(r for r in results if r.source == path)
            self.assertTrue(result.output.name.endswith("-tanpa-latar.png"))
            with Image.open(result.output) as out:
                self.assertEqual(out.mode, "RGBA", name)
                with Image.open(path) as original:
                    self.assertEqual(out.size, original.size)
                alpha = np.asarray(out.getchannel("A"))
                self.assertEqual(alpha.min(), 0, name)
                self.assertEqual(alpha.max(), 255, name)
                self.assertGreater(len(np.unique(alpha)), 2, "tepi harus memiliki nilai alpha bertahap")
        self.assertEqual(before, {p: sha(p) for p in before})
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 100)
        self.assertEqual(len(list(self.out.iterdir())), 3)

    def test_second_run_never_overwrites(self) -> None:
        path = self.save("a.png", factory.product_like()[0])
        first = self.run_batch([path])[0].output
        content = first.read_bytes()
        second = self.run_batch([path])[0].output
        self.assertNotEqual(first, second)
        self.assertEqual(second.name, "a-tanpa-latar (1).png")
        self.assertEqual(first.read_bytes(), content)

    def test_output_in_same_folder_as_source_is_safe(self) -> None:
        path = self.save("foto.png", factory.product_like()[0])
        original = sha(path)
        self.out = path.parent
        result = self.run_batch([path])[0]
        self.assertEqual(result.status, "ok")
        self.assertEqual(sha(path), original)
        self.assertNotEqual(result.output, path)

    def test_cancel_after_first_item(self) -> None:
        files = list(self.make_set().values())
        ctx = TaskContext()
        done = []

        def on_item(result):
            done.append(result)
            ctx.token.cancel()

        ctx.on_item = on_item
        with self.assertRaises(OperationCancelled):
            self.run_batch(files, ctx=ctx)
        self.assertEqual(len(done), 1)
        outputs = list(self.out.iterdir())
        self.assertEqual(len(outputs), 1)
        self.assertGreater(outputs[0].stat().st_size, 0)

    def test_cancel_before_start_creates_nothing(self) -> None:
        path = self.save("a.png", factory.product_like()[0])
        ctx = TaskContext()
        ctx.token.cancel()
        with self.assertRaises(OperationCancelled):
            self.run_batch([path], ctx=ctx)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_cancel_during_inference_stage_leaves_no_file(self) -> None:
        path = self.save("a.png", factory.product_like()[0])
        ctx = TaskContext()
        ctx.on_progress = lambda percent, message: ctx.token.cancel() if percent >= 10 else None
        with self.assertRaises(OperationCancelled):
            self.run_batch([path], ctx=ctx)
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_cancel_from_another_thread(self) -> None:
        files = [self.save(f"g{i}.png", factory.product_like()[0]) for i in range(40)]
        ctx = TaskContext()
        first_item = threading.Event()
        ctx.on_item = lambda result: first_item.set()
        outcome = []

        def work():
            try:
                self.run_batch(files, ctx=ctx)
                outcome.append("selesai")
            except OperationCancelled:
                outcome.append("dibatalkan")

        thread = threading.Thread(target=work)
        thread.start()
        self.assertTrue(first_item.wait(30))
        ctx.token.cancel()
        thread.join(30)
        self.assertEqual(outcome, ["dibatalkan"])
        produced = list(self.out.iterdir())
        self.assertGreaterEqual(len(produced), 1)
        self.assertLess(len(produced), 40)
        for item in produced:
            with Image.open(item) as out:
                out.load()  # tidak ada berkas setengah jadi

    def test_save_failure_is_reported_per_item(self) -> None:
        path = self.save("a.png", factory.product_like()[0])
        with mock.patch.object(Image.Image, "save", side_effect=OSError("disk penuh")):
            result = self.run_batch([path])[0]
        self.assertEqual(result.status, "failed")
        self.assertIn("disimpan", result.message)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_empty_batch_and_missing_model_and_bad_options(self) -> None:
        path = self.save("a.png", factory.product_like()[0])
        with self.assertRaises(ProcessingError):
            self.run_batch([])
        empty = mm.ModelManager(self.tmp / "kosong", [FAKE])
        with self.assertRaises(ModelNotAvailableError):
            pr.run_background_removal(TaskContext(), empty, FAKE, [path], self.out, pr.BackgroundOptions())
        for options in (pr.BackgroundOptions("color", "merah"), pr.BackgroundOptions("image", image_path=None),
                        pr.BackgroundOptions("aneh")):
            with self.subTest(options), self.assertRaises(ProcessingError):
                self.run_batch([path], options)

    def test_works_fully_offline_after_model_is_present(self) -> None:
        path = self.save("a.png", factory.person_like()[0])

        def no_network(*args, **kwargs):
            raise AssertionError("Akses jaringan terdeteksi saat pemrosesan")

        with mock.patch.object(socket.socket, "connect", no_network), \
                mock.patch.object(socket, "create_connection", no_network), \
                mock.patch.object(socket, "getaddrinfo", no_network):
            pr.clear_session_cache()
            result = self.run_batch([path])[0]
        self.assertEqual(result.status, "ok")


class BackgroundReplacementTests(BaseCase):
    def setUp(self) -> None:
        super().setUp()
        self.path = self.save("produk.png", factory.product_like()[0])

    def load_out(self, result):
        with Image.open(result.output) as image:
            return image.copy()

    def test_transparent_is_default(self) -> None:
        out = self.load_out(self.run_batch([self.path])[0])
        self.assertEqual(out.mode, "RGBA")
        self.assertLess(out.getpixel((5, 5))[3], 10)
        self.assertGreaterEqual(out.getpixel((400, 230))[3], 250)  # badan botol terang, hampir opak

    def test_solid_color_replaces_background_and_keeps_alpha_channel(self) -> None:
        out = self.load_out(self.run_batch([self.path], pr.BackgroundOptions("color", "#12AB34"))[0])
        self.assertEqual(out.mode, "RGBA")
        for point in ((5, 5), (795, 5)):
            pixel = out.getpixel(point)
            self.assertEqual(pixel[3], 255)
            for got, want in zip(pixel[:3], (0x12, 0xAB, 0x34)):
                self.assertLessEqual(abs(got - want), 2, point)

    def test_background_image_is_covered_and_cropped(self) -> None:
        wallpaper = Image.new("RGB", (200, 50), (255, 0, 255))
        wallpaper.paste((0, 255, 255), (0, 0, 100, 50))  # kiri cyan, kanan magenta
        wp = self.tmp / "wallpaper.png"
        wallpaper.save(wp)
        out = self.load_out(self.run_batch([self.path], pr.BackgroundOptions("image", image_path=str(wp)))[0])
        self.assertEqual(out.size, (800, 600))
        self.assertEqual(out.getpixel((5, 5))[:3], (0, 255, 255))
        self.assertEqual(out.getpixel((795, 5))[:3], (255, 0, 255))
        self.assertEqual(out.getpixel((5, 5))[3], 255)

    def test_bad_background_image(self) -> None:
        bad = self.tmp / "bukan.png"
        bad.write_text("x", encoding="utf-8")
        with self.assertRaises(Exception):
            self.run_batch([self.path], pr.BackgroundOptions("image", image_path=str(bad)))
        with self.assertRaises(Exception):
            self.run_batch([self.path], pr.BackgroundOptions("image", image_path=str(self.tmp / "hilang.png")))

    def test_apply_background_does_not_mutate_inputs_and_matches_reference(self) -> None:
        rgba = Image.new("RGBA", (40, 30), (10, 20, 30, 128))
        rgba.paste((250, 250, 250, 255), (5, 5, 15, 15))
        background = Image.new("RGBA", (60, 20), (200, 0, 0, 255))
        rgba_before, background_before = rgba.tobytes(), background.tobytes()

        colored = pr.apply_background(rgba, pr.BackgroundOptions("color", "#00FF00"))
        pictured = pr.apply_background(rgba, pr.BackgroundOptions("image", image_path="x"), background)

        self.assertEqual(rgba.tobytes(), rgba_before)
        self.assertEqual(background.tobytes(), background_before)
        reference = Image.alpha_composite(Image.new("RGBA", rgba.size, "#00FF00"), rgba)
        self.assertEqual(colored.tobytes(), reference.tobytes())
        reference = Image.alpha_composite(pr.cover_resize(background, rgba.size), rgba)
        self.assertEqual(pictured.tobytes(), reference.tobytes())
        self.assertIsNot(colored, rgba)

    def test_cover_resize_geometry(self) -> None:
        for source, target in (((200, 50), (80, 80)), ((50, 200), (80, 40)), ((10, 10), (300, 100))):
            self.assertEqual(pr.cover_resize(Image.new("RGBA", source), target).size, target)


class PreviewTests(BaseCase):
    def test_checkerboard_pattern(self) -> None:
        board = pr.checkerboard((48, 24), tile=12)
        self.assertEqual(board.size, (48, 24))
        self.assertNotEqual(board.getpixel((0, 0)), board.getpixel((12, 0)))
        self.assertEqual(board.getpixel((0, 0)), board.getpixel((24, 0)))
        self.assertEqual(board.getpixel((0, 0)), board.getpixel((12, 12)))

    def test_composite_on_checkerboard(self) -> None:
        clear = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
        np.testing.assert_array_equal(
            np.asarray(pr.composite_on_checkerboard(clear).convert("RGB")), np.asarray(pr.checkerboard((30, 30)))
        )
        solid = Image.new("RGBA", (30, 30), (10, 20, 30, 255))
        self.assertEqual(pr.composite_on_checkerboard(solid).getpixel((3, 3)), (10, 20, 30, 255))

    def test_load_preview_is_bounded(self) -> None:
        path = self.save("besar.jpg", Image.new("RGB", (3000, 2000), (50, 60, 70)), "JPEG")
        preview = pr.load_preview(path, 800)
        self.assertEqual(preview.mode, "RGBA")
        self.assertLessEqual(max(preview.size), 800)
        with self.assertRaises(UnsupportedImageError):
            pr.load_preview(self.tmp / "tidak-ada.png")


if __name__ == "__main__":
    unittest.main()
