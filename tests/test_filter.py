import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "current_search_results.html"


class FilterTest(unittest.TestCase):
    def test_converts_current_search_results_to_rss(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=FIXTURE.read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            check=True,
        )

        root = ET.fromstring(result.stdout)
        channel = root.find("channel")
        items = channel.findall("item")

        self.assertEqual(root.tag, "rss")
        self.assertEqual(channel.findtext("title"), "book")
        self.assertEqual(channel.findtext("description"), "book")
        self.assertEqual(
            channel.findtext("link"),
            "https://www.ebay.com/sch/i.html?_nkw=book&_sacat=0&rt=nc",
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].findtext("title"), "Programming & Testing Handbook"
        )
        self.assertEqual(
            items[0].findtext("link"), "https://www.ebay.com/itm/100000000001"
        )
        self.assertEqual(items[0].findtext("guid"), items[0].findtext("link"))
        self.assertEqual(
            items[0].findtext("description"), items[0].findtext("title")
        )


if __name__ == "__main__":
    unittest.main()
