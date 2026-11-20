import unittest

from ui.icon_data import ICON_BODIES
from ui.registry import CATEGORIES, PAGES, get_page, main_pages, other_pages, tool_pages


class RegistryTests(unittest.TestCase):
    def test_page_ids_are_unique(self) -> None:
        ids = [page.page_id for page in PAGES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_sidebar_has_required_items(self) -> None:
        self.assertEqual(
            [page.page_id for page in main_pages()],
            ["dashboard", "qr", "background", "resizer", "converter"],
        )
        self.assertEqual(
            [page.page_id for page in other_pages()], ["recent", "settings", "about"]
        )

    def test_every_page_icon_exists(self) -> None:
        for page in PAGES:
            self.assertIn(page.icon, ICON_BODIES, page.page_id)

    def test_tools_have_description_and_keywords(self) -> None:
        for tool in tool_pages():
            self.assertTrue(tool.description)
            self.assertTrue(tool.keywords)

    def test_unfinished_pages_list_planned_features(self) -> None:
        for page in PAGES:
            if page.group != "home" and page.page_id not in ("settings", "about"):
                self.assertGreaterEqual(len(page.planned), 3, page.page_id)

    def test_categories_reference_existing_tools(self) -> None:
        tool_ids = {tool.page_id for tool in tool_pages()}
        for category in CATEGORIES:
            for tool_id in category.tool_ids:
                self.assertIn(tool_id, tool_ids)
        self.assertEqual(get_page("qr").title, "QR Code Generator")
        with self.assertRaises(KeyError):
            get_page("tidak-ada")


if __name__ == "__main__":
    unittest.main()
