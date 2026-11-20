import ast
import re
import unittest
from pathlib import Path

STYLES = Path(__file__).resolve().parent.parent / "ui" / "styles"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")


def _read(name: str) -> str:
    return (STYLES / f"{name}.qss").read_text(encoding="utf-8")


class StylesheetTests(unittest.TestCase):
    def test_braces_are_balanced_and_no_tokens_left(self) -> None:
        for name in ("light", "dark"):
            text = _read(name)
            self.assertEqual(text.count("{"), text.count("}"), name)
            self.assertNotIn("@", text, name)

    def test_themes_share_the_same_structure(self) -> None:
        self.assertEqual(HEX.sub("#", _read("light")), HEX.sub("#", _read("dark")))

    def test_themes_differ_in_colors(self) -> None:
        self.assertNotEqual(_read("light"), _read("dark"))

    def test_required_states_are_styled(self) -> None:
        text = _read("light")
        for fragment in (":disabled", ":focus", ":hover", ":checked", 'variant="primary"'):
            self.assertIn(fragment, text)


def _luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _block(text: str, selector: str) -> dict[str, str]:
    """Mengambil properti dari blok QSS yang selektornya persis `selector`."""
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", text)
    assert match, f"blok tidak ditemukan: {selector}"
    return dict(re.findall(r"([\w-]+):\s*([^;]+);", match.group(1)))


class ThemeContrastTests(unittest.TestCase):
    """Teks normal harus berkontras minimal 4,5 banding 1 (WCAG AA) pada kedua tema."""

    def test_text_pairs_meet_aa(self) -> None:
        for name in ("light", "dark"):
            text = _read(name)
            card = _block(text, "QFrame#Card, QFrame#ToolCard")["background-color"]
            nav = _block(text, "QPushButton#NavButton:checked")
            ghost = _block(text, 'QPushButton[variant="ghost"]')
            primary = _block(text, 'QPushButton[variant="primary"]')
            hover = _block(text, 'QPushButton[variant="primary"]:hover')
            label = _block(text, "QLabel")["color"]
            muted = _block(text, "QLabel#Muted")["color"]
            alt = _block(text, "QFrame#ToolCard:hover")["background-color"]
            pairs = {
                "menu aktif": (nav["color"], nav["background-color"]),
                "tombol ghost": (ghost["color"], card),
                "tombol utama": (primary["color"], primary["background-color"]),
                "tombol utama hover": (hover["color"] if "color" in hover else primary["color"], hover["background-color"]),
                "teks utama": (label, card),
                "teks redup di kartu": (muted, card),
                "teks redup di kartu hover": (muted, alt),
            }
            for label_text, (fg, bg) in pairs.items():
                with self.subTest(tema=name, pasangan=label_text):
                    self.assertGreaterEqual(_contrast(fg, bg), 4.5, f"{fg} di atas {bg}")

    def test_disabled_states_exist_for_all_form_controls(self) -> None:
        for name in ("light", "dark"):
            text = _read(name)
            for fragment in ("QRadioButton:disabled", "QCheckBox:disabled", "QFrame#DropZone:disabled", "QSpinBox:disabled"):
                with self.subTest(tema=name, selektor=fragment):
                    self.assertIn(fragment, text)

    def test_python_palette_matches_stylesheets(self) -> None:
        source = (Path(__file__).resolve().parent.parent / "ui" / "theme.py").read_text(encoding="utf-8")
        palettes = ast.literal_eval(re.search(r"PALETTES[^=]*=\s*(\{.*?\n\})", source, re.S).group(1))
        for name in ("light", "dark"):
            text, colors = _read(name), palettes[name]
            checks = {
                "surface": _block(text, "QFrame#Card, QFrame#ToolCard")["background-color"],
                "text": _block(text, "QLabel")["color"],
                "muted": _block(text, "QLabel#Muted")["color"],
                "accent": _block(text, 'QPushButton[variant="primary"]')["background-color"],
                "accent_text": _block(text, 'QPushButton[variant="ghost"]')["color"],
                "bg": _block(text, "QMainWindow, QStackedWidget, QScrollArea, QWidget#PageRoot")["background-color"],
            }
            for key, expected in checks.items():
                with self.subTest(tema=name, kunci=key):
                    self.assertEqual(colors[key].upper(), expected.upper())


if __name__ == "__main__":
    unittest.main()
