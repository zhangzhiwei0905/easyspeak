import unittest
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.daily import DailyContent
from app.routers.daily import _build_content_list_item


class DailyCategoryFilterTest(unittest.TestCase):
    def test_list_item_includes_category_fields(self):
        content = DailyContent(
            id=1,
            date=date(2026, 4, 26),
            theme_zh="机场出行",
            theme_en="At the Airport",
            category="travel",
            category_zh="旅行出行",
        )
        content.phrases = []
        content.words = []

        item = _build_content_list_item(content)

        self.assertEqual(item.category, "travel")
        self.assertEqual(item.category_zh, "旅行出行")


if __name__ == "__main__":
    unittest.main()
