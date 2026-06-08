import json
import os
import re
import ssl
import subprocess
import sys
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "current_search_results.html"
# Quotes make the live query narrower, although eBay can still return a few
# non-promoted variation listings whose titles do not contain "book".
LIVE_URL = "https://www.ebay.com/sch/i.html?_nkw=%22book%22&_sacat=0"


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

    def test_escapes_search_query_in_channel_metadata(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            'name="_nkw" value="book"',
            'name="_nkw" value="books &amp; magazines"',
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        channel = ET.fromstring(result.stdout).find("channel")
        self.assertEqual(channel.findtext("title"), "books & magazines")
        self.assertEqual(channel.findtext("description"), "books & magazines")


@unittest.skipUnless(
    os.environ.get("EBAY_LIVE_TEST") == "1",
    "set EBAY_LIVE_TEST=1 to make a real eBay request",
)
class LiveFilterTest(unittest.TestCase):
    def test_converts_live_book_search_results_to_rss(self):
        request = urllib.request.Request(
            LIVE_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_html = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            # Anti-automation responses are environmental, not parser failures.
            if error.code in (403, 429):
                self.skipTest(f"eBay blocked the live request with HTTP {error.code}")
            raise
        except urllib.error.URLError as error:
            # Some local Python installations do not trust the system proxy CA.
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                self.skipTest(f"local TLS verification failed: {error.reason}")
            raise

        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=raw_html,
            text=True,
            capture_output=True,
            check=True,
        )

        channel = ET.fromstring(result.stdout).find("channel")
        items = channel.findall("item")
        self.assertIn("book", channel.findtext("title").lower())
        self.assertGreater(len(items), 0)

        # Read eBay's source metadata independently, then prove that none of the
        # promoted listing IDs survived conversion into RSS items.
        listings_match = re.search(
            r'"listings"\s*:\s*(\[.*?\])',
            raw_html,
            re.DOTALL,
        )
        listing_metadata = json.loads(listings_match.group(1))
        promoted_listing_ids = {
            str(listing["itemId"])
            for listing in listing_metadata
            if listing.get("promoted")
        }

        for item in items:
            self.assertIn("/itm/", item.findtext("link"))
            self.assertEqual(item.findtext("guid"), item.findtext("link"))
            listing_id = item.findtext("link").rstrip("/").rsplit("/", 1)[-1]
            self.assertNotIn(listing_id, promoted_listing_ids)


if __name__ == "__main__":
    unittest.main()
