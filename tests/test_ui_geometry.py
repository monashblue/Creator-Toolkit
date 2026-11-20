import unittest

from ui.geometry import clamp_ratio, divider_x, fit_rect, ratio_from_x


class GeometryTests(unittest.TestCase):
    def test_fit_rect_keeps_aspect_and_centers(self) -> None:
        self.assertEqual(fit_rect(200, 100, 400, 400), (0, 100, 400, 200))
        self.assertEqual(fit_rect(100, 200, 400, 400), (100, 0, 200, 400))
        x, y, w, h = fit_rect(640, 800, 300, 300)
        self.assertAlmostEqual(w / h, 640 / 800, places=1)
        self.assertLessEqual(w, 300)
        self.assertLessEqual(h, 300)
        self.assertEqual(x, (300 - w) // 2)

    def test_fit_rect_handles_degenerate_sizes(self) -> None:
        self.assertEqual(fit_rect(0, 10, 100, 100), (0, 0, 0, 0))
        self.assertEqual(fit_rect(10, 10, 0, 100), (0, 0, 0, 0))

    def test_ratio_roundtrip_and_clamp(self) -> None:
        self.assertEqual(clamp_ratio(-3), 0.0)
        self.assertEqual(clamp_ratio(7), 1.0)
        self.assertEqual(divider_x(50, 200, 0.5), 150)
        self.assertEqual(divider_x(50, 200, 2.0), 250)
        self.assertAlmostEqual(ratio_from_x(150, 50, 200), 0.5)
        self.assertEqual(ratio_from_x(10, 50, 200), 0.0)
        self.assertEqual(ratio_from_x(999, 50, 200), 1.0)
        self.assertEqual(ratio_from_x(5, 50, 0), 0.5)


if __name__ == "__main__":
    unittest.main()
