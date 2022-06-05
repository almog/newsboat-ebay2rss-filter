items = selector.css('.srp-river .srp-river-results .s-item__wrapper')
test_item = items[0]

title = item.css(".s-item__title::text").get()
link =  item.css(".s-item__link").attrib['href']
price = item.css(".s-item__price::text").get()
condition = item.css(".SECONDARY_INFO::text").get()
seller_info = bidding_option = item.css(".s-item__time-left").get()
bin_or_offer = item.css(".s-item__purchase-options-with-icon::text").get() # "Buy It Now" | "or Best Offer" | non existing if it's a bid
is_classified_ad = bool(item.css('.lvformat::text').get())

shipping_fee_info_selector = items[0].css('.s-item__shipping.s-item__logisticsCost')
shipping_cost = shipping_fee_info_selector.css('span::text').get()
free_shipping = shipping_fee_info_selector.css('::text').get() 
shipping_cost = shipping_cost or free_shipping
