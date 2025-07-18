# Nyaastats

Track download statistics from the nyaa torrent tracker over time in a sqlite db. Besides
the raw stats by infohash, structured metadata is extracted from torrent filenames using
[guessit](https://github.com/guessit-io/guessit), to make it easier to aggregate
across episodes and encodes/release groups.

## Why

Download stats are interesting market research that you can publicly monitor
(unlike e.g. netflix or crunchyroll). Nyaa downloaders are more aligned to my
particular subculture of anime fandom anyway, vs the normies on MAL or whatever.

## Where data?

I'll publish the sqlite database at some point along with some nice plots for visualization.
Meanwhile you can run the code yourself if you want and do your own SQL queries.

## How it works

This is a python project with dependencies managed by [uv](https://docs.astral.sh/uv/).
Run it in cron to periodically check for new torrents from nyaa's RSS feed (only
english-translated torrents by default) and scrape the download stats (plus
seeders/leechers since we get that for free) into a sqlite database for torrents
that are due for scraping. "Due" is determined by a time-decay algorithm, i.e.
new torrents are scraped every hour, decaying to weekly scraping for old torrents, since
most of the download stats happen early on.

To backfill data beyond the 75 torrents that nyaa's RSS feed provides, you can run
the `nyaastats-backfill` script, which adds more infohashes to the database by scraping
HTML pages on nyaa.

```bash
# cron setup exmaple
echo "0 * * * * cd /path/to/nyaastats && uv run nyaastats" | crontab -

# Backfill last 100 pages of english-translated torrents
uv run nyaastats-backfill

# Backfill specific user or search query
uv run nyaastats-backfill --url "https://nyaa.si/user/subsplease"
uv run nyaastats-backfill --url "https://nyaa.si/?f=0&c=1_2&q=underwater"
```

### Implementation

95% of the code was slopped up by claude. I did guide the initial design more heavily and I think
I have generally good engineering taste, but I definitely didn't scrutinize every line of code.
Such is modern software dev.
