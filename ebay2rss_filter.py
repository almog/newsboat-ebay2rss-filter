#!/usr/bin/env python3

import sys
import traceback
import re

from parsel import Selector
from html import escape

try:
    raw_html = sys.stdin.read()
    assert len(raw_html) > 0, "Filter input must not be empty"

    document = Selector(text=raw_html)
    assert not document.css('div :contains("There seems to be a problem serving the request at this time")'), "Ebay temporary error page returned"

    no_exact_match_texts = (
            'We’ve streamlined your search results to show you the best listings',
            'No exact matches found')

    has_exact_results = all(not document.css(f':contains("{text}")') for text in no_exact_match_texts)

    feed_description = feed_title = document.css('input[name="_nkw"]').attrib['value']
    feed_link = re.search(r'baseUrl":"(https://.*?")', raw_html).group(1) #TODO: use the document rather than raw HTML


    items = document.css('.srp-river .srp-river-results .s-item__wrapper') if has_exact_results else []

    print(f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
    <title>{feed_title}</title>
    <description>{feed_title}</description>
    <link>{escape(feed_link)}</link>""")

    for item in items:
        title = item.css(".s-item__title span[role=heading]::text").get()
        link = item.css(".s-item__link").attrib['href']
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
    with open('ebay2rss.log', 'a') as log:
        log.write(f'{raw_html=}\n')
        log.write(f'{sys.argv=}\n')
        log.write(f'{type(err)}: {err}\n')
        log.write(traceback.format_exc())
        raise
