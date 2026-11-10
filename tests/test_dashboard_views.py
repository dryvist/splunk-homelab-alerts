import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "default/data/ui/views"


def view_input_tokens(path):
    """The form tokens a view declares, used by the alert-link test."""
    root = ElementTree.parse(path).getroot()
    return {element.get("token") for element in root.iter("input") if element.get("token")}


class DashboardViewsTest(unittest.TestCase):
    def test_every_view_is_a_form_with_a_label_and_a_time_token(self):
        views = sorted(VIEWS.glob("*.xml"))
        self.assertTrue(views)
        for path in views:
            root = ElementTree.parse(path).getroot()
            self.assertEqual(root.tag, "form", path.name)
            self.assertIsNotNone(root.find("label"), path.name)
            self.assertIn("time", view_input_tokens(path), path.name)

    def test_every_panel_search_is_bounded_by_the_time_token(self):
        for path in sorted(VIEWS.glob("*.xml")):
            root = ElementTree.parse(path).getroot()
            for search in root.iter("search"):
                earliest = search.find("earliest")
                latest = search.find("latest")
                self.assertIsNotNone(earliest, path.name)
                self.assertEqual(earliest.text, "$time.earliest$", path.name)
                self.assertIsNotNone(latest, path.name)
                self.assertEqual(latest.text, "$time.latest$", path.name)


if __name__ == "__main__":
    unittest.main()
