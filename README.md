# Why?
For over 15 years and until [Not long ago](https://community.ebay.com/t5/Buying/RSS-feed-support-gone-for-good/td-p/32841248) the `_rss=1` query string instructed any ebay `/sch` to respond with an RSS feed. 
For a while an altenative endpoint [/dsc](https://community.ebay.com/t5/Share-eBay-Technical-Issues/RSS-is-no-longer-available/td-p/32834076) seemed to still be supporting the `_rss=1` parameter, yet this support too has been removed by now, which leaves us with no official RSS feed for ebay search queries.


# What?
This is really just a Newsboat _filter_ that translates ebay search results into an RSS feed

# But why is this Newboat specific, why not something more generic?
You're right to ask that, my initial thought was to write a lightweight translation service (an http proxy) that takes an ebay URL and seemlessly returns a feed.
But since I have multiple ebay URLs on Newsboat, such service would have to handle concurrency and throttling related issues which Newsboat already does, and I rather keep it that way, for now at least.
And with that in mind, by using a filter (rather than exec script), I let Snowboat be in charge of request handling. 


# Usage
```
$ pip install parsel
$ git clone https://github.com/almog/newsboat-ebay2rss-filter/blob/main/ebay2rss_filter.py

```

## Simple search query:
```
"filter:~/<eaby2rss-path>/ebay2rss_filter.py:https://www.ebay.com/sch/i.html?&_nkw=test"
```
## Migrating existing newsboat `urls` file
`./migrate_urls <input_file> <filter_path>` transforms any ebay.com `urls` file to work with the ebay2rss filter (output is written to `stdio`)

```
./migrate_urls ~/.newsboat/urls ~/proj/newsboat-ebay2rss-filter/ebay2rss_filter.py > ./transformed_urls
```
Reads a `urls` file, a filter path and writes a new file `./transformed_url`.

## Logging
Note that Newsboat filters error log is not written to Newsboat error log, the filter however logs all errors to `~/.newsboat/ebay2rss.log` directly.
