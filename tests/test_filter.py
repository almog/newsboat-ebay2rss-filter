import http.cookiejar
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "current_search_results.html"
NO_EXACT_MATCHES_FIXTURE = (
    ROOT / "tests" / "fixtures" / "current_no_exact_matches.html"
)
# Quotes make the live query narrower, although eBay can still return a few
# non-promoted variation listings whose titles do not contain "book".
LIVE_URL = "https://www.ebay.com/sch/i.html?_nkw=%22book%22&_sacat=0"
LIVE_NO_EXACT_MATCHES_URL = (
    "https://www.ebay.com/sch/i.html?"
    "_nkw=%22ultraviolet+accordion+teacup+qzjxk%22&_sacat=0"
)
LIVE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)


class EbayRequestBlocked(Exception):
    pass


class FilterTest(unittest.TestCase):
    def run_filter_with_isolated_home(self, raw_html):
        with tempfile.TemporaryDirectory() as home:
            return subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input=raw_html,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                },
            )

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
            items[0].findtext("description"),
            (
                "Programming & Testing Handbook\n"
                "Price: ILS 186.02\n"
                "Condition: Brand New\n"
                "Listing type: Buy It Now\n"
                "Shipping: +ILS 24.50 delivery"
            ),
        )
        self.assertNotIn("56 watchers", items[0].findtext("description"))

    def test_omits_optional_condition_and_shipping(self):
        html = (
            FIXTURE.read_text(encoding="utf-8")
            .replace("s-card__subtitle-row", "removed-subtitle-row")
            .replace("+ILS 24.50 delivery", "Free returns")
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        description = (
            ET.fromstring(result.stdout)
            .find("channel")
            .find("item")
            .findtext("description")
        )
        self.assertEqual(
            description,
            (
                "Programming & Testing Handbook\n"
                "Price: ILS 186.02\n"
                "Listing type: Buy It Now"
            ),
        )

    def test_normalizes_fixed_price_best_offer_listing_type(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            "Buy It Now",
            "or Best Offer",
            1,
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        description = (
            ET.fromstring(result.stdout)
            .find("channel")
            .find("item")
            .findtext("description")
        )
        self.assertIn(
            "Listing type: Buy It Now · Best Offer",
            description,
        )

    def test_normalizes_combined_listing_types(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            (
                '<span class="su-styled-text secondary large">'
                "Buy It Now</span>"
            ),
            (
                '<span class="su-styled-text secondary large">'
                "3 bids · Time left 2h left</span></div>"
                '<div class="s-card__attribute-row">'
                '<span class="su-styled-text secondary large">'
                "Buy It Now</span></div>"
                '<div class="s-card__attribute-row">'
                '<span class="su-styled-text secondary large">'
                "or Best Offer</span>"
            ),
            1,
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        description = (
            ET.fromstring(result.stdout)
            .find("channel")
            .find("item")
            .findtext("description")
        )
        self.assertIn(
            "Listing type: Bid · Buy It Now · Best Offer",
            description,
        )
        self.assertNotIn("3 bids", description)
        self.assertNotIn("Time left", description)

    def test_excludes_suggested_results_when_no_exact_matches_exist(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=NO_EXACT_MATCHES_FIXTURE.read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            check=True,
        )

        channel = ET.fromstring(result.stdout).find("channel")
        self.assertEqual(
            channel.findtext("title"),
            '"ultraviolet accordion teacup qzjxk"',
        )
        self.assertEqual(channel.findall("item"), [])

    def test_keeps_results_after_streamlined_search_notice(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            "<ul",
            (
                '<section class="section-notice">'
                "We’ve streamlined your search results to show you the best "
                "listings. See more results"
                "</section><ul"
            ),
            1,
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        channel = ET.fromstring(result.stdout).find("channel")
        self.assertEqual(len(channel.findall("item")), 1)

    def test_excludes_results_matching_fewer_words(self):
        html = (
            FIXTURE.read_text(encoding="utf-8")
            .replace(
                (
                    '<li class="s-card s-card--horizontal" '
                    'data-listingid="100000000002">'
                ),
                (
                    '<li class="srp-river-answer '
                    'srp-river-answer--REWRITE_START">'
                    "Results matching fewer words"
                    "</li>"
                    '<li class="s-card s-card--horizontal" '
                    'data-listingid="100000000002">'
                ),
                1,
            )
            .replace(
                ',\n          {"itemId":100000000002,"promoted":true}',
                "",
                1,
            )
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=html,
            text=True,
            capture_output=True,
            check=True,
        )

        items = ET.fromstring(result.stdout).find("channel").findall("item")
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].findtext("link"),
            "https://www.ebay.com/itm/100000000001",
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

    def test_rejects_missing_search_base_url(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            '"baseUrl"',
            '"removedBaseUrl"',
            1,
        )
        result = self.run_filter_with_isolated_home(html)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("eBay search baseUrl not found", result.stderr)

    def test_rejects_non_string_search_base_url(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            (
                '"baseUrl":'
                '"https://www.ebay.com/sch/i.html?'
                '_nkw=book&_sacat=0&rt=nc"'
            ),
            '"baseUrl":123',
            1,
        )
        result = self.run_filter_with_isolated_home(html)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "eBay search baseUrl must be a JSON string",
            result.stderr,
        )

    def test_rejects_invalid_search_base_url(self):
        valid_url = (
            "https://www.ebay.com/sch/i.html?"
            "_nkw=book&_sacat=0&rt=nc"
        )
        invalid_urls = (
            "http://www.ebay.com/sch/i.html?_nkw=book",
            "https://example.com/sch/i.html?_nkw=book",
            "https://www.ebay.com/itm/100000000001",
        )

        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                html = FIXTURE.read_text(encoding="utf-8").replace(
                    valid_url,
                    invalid_url,
                    1,
                )
                result = self.run_filter_with_isolated_home(html)

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(
                    "eBay search baseUrl is not an eBay search URL",
                    result.stderr,
                )

    def test_logs_errors_to_newsboat_directory(self):
        with tempfile.TemporaryDirectory() as home:
            raw_html = "response body must not be logged"
            result = subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input=raw_html,
                text=True,
                capture_output=True,
                cwd=home,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            log_path = Path(home) / ".newsboat" / "ebay2rss.log"
            self.assertTrue(log_path.exists())
            log = log_path.read_text(encoding="utf-8")
            self.assertNotIn(raw_html, log)
            self.assertIn("Traceback", log)

    def test_logs_errors_to_configured_path(self):
        with tempfile.TemporaryDirectory() as home:
            log_path = Path(home) / "slowlog"
            result = subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input="invalid response",
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                    "EBAY2RSS_LOG": str(log_path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Traceback", log_path.read_text(encoding="utf-8"))
            self.assertFalse(
                (Path(home) / ".newsboat" / "ebay2rss.log").exists()
            )

    def test_does_not_log_keyboard_interrupt(self):
        with (
            tempfile.TemporaryDirectory() as home,
            tempfile.TemporaryDirectory() as modules,
        ):
            Path(modules, "parsel.py").write_text(
                "class Selector:\n"
                "    def __init__(self, *args, **kwargs):\n"
                "        raise KeyboardInterrupt\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input="<html></html>",
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join([modules, *sys.path]),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(home) / ".newsboat" / "ebay2rss.log").exists())

    def test_rejects_results_without_promotion_metadata(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            '"listings":',
            '"removedListings":',
            1,
        )
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input=html,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("eBay listing metadata not found", result.stderr)

    def test_rejects_result_missing_from_listing_metadata(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            ',\n          {"itemId":100000000002,"promoted":true}',
            "",
            1,
        )
        result = self.run_filter_with_isolated_home(html)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            "eBay listing metadata missing for 100000000002",
            result.stderr,
        )

    def test_rejects_incomplete_result_before_emitting_rss(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            'href="https://www.ebay.com/itm/100000000001?'
            '_skw=book&amp;tracking=fake"',
            'data-missing-href=""',
            1,
        )
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [sys.executable, str(ROOT / "ebay2rss_filter.py")],
                input=html,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn(
                "eBay result 100000000001 has no link",
                result.stderr,
            )

    def test_rejects_ebay_error_page_with_optimized_python(self):
        html = FIXTURE.read_text(encoding="utf-8").replace(
            "<body>",
            (
                "<body><div><span>"
                "There seems to be a problem serving the request at this time"
                "</span></div>"
            ),
            1,
        )
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [sys.executable, "-O", str(ROOT / "ebay2rss_filter.py")],
                input=html,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(sys.path),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Ebay temporary error page returned", result.stderr)

    def test_rejects_ebay_anti_bot_challenge(self):
        html = (
            "<html><head><title>Pardon Our Interruption...</title></head>"
            "<body>Checking your browser before accessing eBay.</body></html>"
        )
        result = self.run_filter_with_isolated_home(html)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("eBay anti-bot challenge page returned", result.stderr)


@unittest.skipUnless(
    os.environ.get("EBAY_LIVE_TEST") == "1",
    "set EBAY_LIVE_TEST=1 to make a real eBay request",
)
class LiveFilterTest(unittest.TestCase):
    def build_opener(self):
        system_ca = Path("/etc/ssl/cert.pem")
        if (
            sys.platform == "darwin"
            and "SSL_CERT_FILE" not in os.environ
            and system_ca.exists()
        ):
            ssl_context = ssl.create_default_context(cafile=system_ca)
        else:
            ssl_context = ssl.create_default_context()

        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=ssl_context),
        )

    def fetch_page(self, opener, url, referer=None):
        headers = {
            "User-Agent": LIVE_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Upgrade-Insecure-Requests": "1",
        }
        if referer:
            headers["Referer"] = referer

        try:
            request = urllib.request.Request(url, headers=headers)
            with opener.open(request, timeout=30) as response:
                if "/splashui/challenge" in response.url:
                    raise EbayRequestBlocked("eBay challenged the live request")
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                raise EbayRequestBlocked(
                    f"eBay blocked the live request with HTTP {error.code}"
                ) from error
            raise
        except urllib.error.URLError as error:
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                self.skipTest(f"local TLS verification failed: {error.reason}")
            raise

    def fetch_ebay_search(self, url):
        for attempt in range(2):
            opener = self.build_opener()
            try:
                self.fetch_page(opener, "https://www.ebay.com/")
                return self.fetch_page(
                    opener,
                    url,
                    referer="https://www.ebay.com/",
                )
            except EbayRequestBlocked as error:
                if attempt == 1:
                    self.skipTest(str(error))
                time.sleep(5)

    def run_filter(self, raw_html):
        return subprocess.run(
            [sys.executable, str(ROOT / "ebay2rss_filter.py")],
            input=raw_html,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_converts_live_book_search_results_to_rss(self):
        raw_html = self.fetch_ebay_search(LIVE_URL)
        result = self.run_filter(raw_html)

        channel = ET.fromstring(result.stdout).find("channel")
        items = channel.findall("item")
        self.assertIn("book", channel.findtext("title").lower())
        self.assertGreater(len(items), 0)
        descriptions = [item.findtext("description") for item in items]
        for label in ("Price", "Condition", "Listing type", "Shipping"):
            self.assertTrue(
                any(f"\n{label}: " in description for description in descriptions),
                f"no live item description included {label.lower()} details",
            )

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

    def test_excludes_live_suggested_results_when_no_exact_matches_exist(self):
        raw_html = self.fetch_ebay_search(LIVE_NO_EXACT_MATCHES_URL)
        self.assertIn("No exact matches found", raw_html)

        channel = ET.fromstring(self.run_filter(raw_html).stdout).find("channel")
        self.assertEqual(channel.findall("item"), [])


if __name__ == "__main__":
    unittest.main()
