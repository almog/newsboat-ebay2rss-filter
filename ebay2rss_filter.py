#!/usr/bin/env python3

import json
import sys
import traceback
import re
from pathlib import Path

from parsel import Selector
from html import escape

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
    listing_metadata = json.loads(listings_match.group(1)) if listings_match else []
    promoted_listing_ids = {
        str(listing["itemId"])
        for listing in listing_metadata
        if listing.get("promoted")
    }

    items = document.css('li.s-card[data-listingid]') if has_exact_results else []

    print(f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
    <title>{escape(feed_title)}</title>
    <description>{escape(feed_title)}</description>
    <link>{escape(feed_link)}</link>""")

    for item in items:
        if item.attrib.get("data-listingid") in promoted_listing_ids:
            continue

        title = item.css(".s-card__title .su-styled-text::text").get()
        if title == "Shop on eBay":
            continue

        link = item.css(".s-card__link::attr(href)").get()
        link = re.sub(r"\?.*", "", link)
        # TODO: Add these fields to each item:
        #price = item.css(".s-item__price::text").get()
        #condition = item.css(".SECONDARY_INFO::text").get()
        #seller_info = bidding_option = item.css(".s-item__time-left").get()
        #bin_or_offer = item.css(".s-item__purchase-options-with-icon::text").get() # "Buy It Now" | "or Best Offer" | non existing if it's a bid
        #is_classified_ad = bool(item.css('.lvformat::text').get())

        #shipping_fee_info_selector = items[0].css('.s-item__shipping.s-item__logisticsCost')
        #shipping_cost = shipping_fee_info_selector.css('span::text').get()
        #free_shipping = shipping_fee_info_selector.css('::text').get() 
        #shipping_cost = shipping_cost or free_shipping
        print(f"""
        <item>
        <title>{escape(title)}</title>
        <link>{escape(link)}</link>
        <guid>{escape(link)}</guid>
        <description>{escape(title)}</description>
        </item>""")

    print("""
    </channel>
    </rss>""")

except BaseException as err:
    log_path = Path.home() / ".newsboat" / "ebay2rss.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f'{raw_html=}\n')
        log.write(f'{sys.argv=}\n')
        log.write(f'{type(err)}: {err}\n')
        log.write(traceback.format_exc())
        raise
