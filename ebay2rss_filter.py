#!/usr/bin/env python3

import json
import sys
import traceback
import re
from pathlib import Path

from parsel import Selector
from html import escape


SHIPPING_TERMS = (
    "shipping",
    "delivery",
    "postage",
)


def normalized_text(selector):
    text = " ".join(selector.css("::text").getall())
    return " ".join(text.split())


def is_shipping_detail(text):
    return any(term in text.lower() for term in SHIPPING_TERMS)


def extract_listing_type(item, listing_id):
    attributes = normalized_text(
        item.css(".su-card-container__attributes__primary")
    )
    if not attributes:
        raise ValueError(f"eBay result {listing_id} has no listing type")

    attributes = attributes.lower()
    has_bid = "time left" in attributes
    has_best_offer = "best offer" in attributes
    has_buy_it_now = "buy it now" in attributes or (
        has_best_offer and not has_bid
    )

    listing_types = []
    if has_bid:
        listing_types.append("Bid")
    if has_buy_it_now:
        listing_types.append("Buy It Now")
    if has_best_offer:
        listing_types.append("Best Offer")
    if not listing_types:
        raise ValueError(f"eBay result {listing_id} has no listing type")
    return " · ".join(listing_types)


def extract_condition(item, listing_id):
    subtitle_rows = item.css(".s-card__subtitle-row")
    if not subtitle_rows:
        # Some listings genuinely omit condition from eBay search results.
        return None

    # Promotional subtitles may precede the condition, which is the final row.
    condition_elements = subtitle_rows[-1].css(
        ".s-card__subtitle .su-styled-text"
    )
    if not condition_elements:
        raise ValueError(f"eBay result {listing_id} has malformed condition")

    condition = normalized_text(condition_elements[0])
    if not condition:
        raise ValueError(f"eBay result {listing_id} has empty condition")
    return condition.rstrip(" ·")


def extract_listing_details(item, listing_id):
    attribute_rows = item.css(
        ".su-card-container__attributes__primary "
        "> .s-card__attribute-row"
    )
    attribute_texts = []
    for row in attribute_rows:
        text = normalized_text(row)
        if not text:
            raise ValueError(f"eBay result {listing_id} has an empty attribute")
        attribute_texts.append(text)

    shipping = next(
        (text for text in attribute_texts if is_shipping_detail(text)),
        None,
    )
    price = normalized_text(item.css(".s-card__price"))
    if not price:
        raise ValueError(f"eBay result {listing_id} has no price")

    return {
        "Price": price,
        "Condition": extract_condition(item, listing_id),
        "Listing type": extract_listing_type(item, listing_id),
        # Digital listings can legitimately omit shipping from search results.
        "Shipping": shipping,
    }


def format_item_description(title, details):
    lines = [title]
    lines.extend(
        f"{label}: {value}"
        for label, value in details.items()
        if value
    )
    return "\n".join(lines)


try:
    raw_html = sys.stdin.read()
    if not raw_html:
        raise ValueError("Filter input must not be empty")

    document = Selector(text=raw_html)
    if document.css(
        'div :contains("There seems to be a problem serving the request at this time")'
    ):
        raise ValueError("Ebay temporary error page returned")

    no_exact_match_texts = (
            'We’ve streamlined your search results to show you the best listings',
            'No exact matches found')

    has_exact_results = all(not document.css(f':contains("{text}")') for text in no_exact_match_texts)

    feed_description = feed_title = document.css('input[name="_nkw"]').attrib['value']
    feed_link = re.search(r'baseUrl":"(https://.*?)"', raw_html).group(1) #TODO: use the document rather than raw HTML

    # eBay embeds search state in a script shaped like:
    #   $M_...=(window.$M_...||[]).concat({"...":{"mainSearchContext":{
    #     "listings":[{"itemId":123, "promoted":true}, ...]}}})
    # The visible "Sponsored" marker is obfuscated and appears on every card, so
    # use this listings array as the authoritative promoted flag keyed by ID.
    listings_match = re.search(
        r'"listings"\s*:\s*(\[.*?\])',
        raw_html,
        re.DOTALL,
    )
    items = document.css('li.s-card[data-listingid]') if has_exact_results else []
    if items and not listings_match:
        raise ValueError("eBay listing metadata not found")

    listing_metadata = json.loads(listings_match.group(1)) if listings_match else []
    listing_metadata_ids = {
        str(listing["itemId"])
        for listing in listing_metadata
    }
    result_listing_ids = {
        item.attrib["data-listingid"]
        for item in items
        if item.css(".s-card__title .su-styled-text::text").get() != "Shop on eBay"
    }
    # Assume every result ID is represented in this metadata. If that subset
    # relationship breaks, eBay's metadata structure or its meaning has changed.
    missing_listing_ids = result_listing_ids - listing_metadata_ids
    if missing_listing_ids:
        missing_listing_id = sorted(missing_listing_ids)[0]
        raise ValueError(f"eBay listing metadata missing for {missing_listing_id}")

    promoted_listing_ids = {
        str(listing["itemId"])
        for listing in listing_metadata
        if listing.get("promoted")
    }

    feed_items = []
    for item in items:
        listing_id = item.attrib["data-listingid"]
        if listing_id in promoted_listing_ids:
            continue

        title = item.css(".s-card__title .su-styled-text::text").get()
        if title == "Shop on eBay":
            continue
        if not title:
            raise ValueError(f"eBay result {listing_id} has no title")

        link = item.css(".s-card__link::attr(href)").get()
        if not link:
            raise ValueError(f"eBay result {listing_id} has no link")
        link = re.sub(r"\?.*", "", link)

        description = format_item_description(
            title,
            extract_listing_details(item, listing_id),
        )
        feed_items.append((title, link, description))

    print(f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
    <title>{escape(feed_title)}</title>
    <description>{escape(feed_title)}</description>
    <link>{escape(feed_link)}</link>""")

    for title, link, description in feed_items:
        print(f"""
        <item>
        <title>{escape(title)}</title>
        <link>{escape(link)}</link>
        <guid>{escape(link)}</guid>
        <description>{escape(description)}</description>
        </item>""")

    print("""
    </channel>
    </rss>""")

except Exception as err:
    log_path = Path.home() / ".newsboat" / "ebay2rss.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f'{sys.argv=}\n')
        log.write(f'{type(err)}: {err}\n')
        log.write(traceback.format_exc())
        raise
