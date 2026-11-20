import unittest
import xml.etree.ElementTree as ET

from ui.icon_data import ICON_BODIES, build_svg


class IconDataTests(unittest.TestCase):
    def test_all_icons_are_valid_xml(self) -> None:
        for name in ICON_BODIES:
            root = ET.fromstring(build_svg(name, "#4F46E5"))
            self.assertTrue(root.tag.endswith("svg"), name)
            self.assertEqual(root.get("viewBox"), "0 0 24 24")
            self.assertEqual(root.get("stroke"), "#4F46E5")

    def test_unknown_icon_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_svg("tidak-ada", "#000000")


if __name__ == "__main__":
    unittest.main()
