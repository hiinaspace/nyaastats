# About Nyaastats

Nyaastats tracks download statistics for anime torrents from [Nyaa.si](https://nyaa.si), the largest anime torrent tracker.

## How It Works

1. **Data Collection**: A Python scraper runs hourly to collect torrent metadata and download statistics from Nyaa's RSS feed and BitTorrent trackers.

2. **ETL Pipeline**: Weekly, an ETL pipeline processes the raw data:
   - Matches torrents to anime shows using fuzzy title matching against the [AniList](https://anilist.co) database
   - Aggregates downloads across multiple torrent releases (different groups, resolutions, etc.)
   - Calculates daily and weekly statistics
   - Exports processed data as Parquet and JSON files

3. **Visualization**: This website uses [Observable Framework](https://observablehq.com/framework) to create interactive visualizations from the processed data.

## Data Coverage

Currently tracking:
- **Fall 2025** season (complete)
- **Winter 2026** season (ongoing)

## Methodology

### Download Counting
- Downloads are tracked from the BitTorrent tracker's "completed downloads" metric
- Statistics are aggregated across all torrent versions of an episode (different groups, resolutions, etc.)
- **Assumption**: The average viewer downloads only one version per episode, so summing across torrents approximates unique viewers

### Fuzzy Matching
- Torrent titles are matched to AniList shows using edit distance (Levenshtein)
- Manual overrides handle edge cases where auto-matching fails
- Batch torrents and v2 torrents are excluded to avoid double-counting

### Time Normalization
- Episode statistics are normalized to "days since first torrent release"
- This allows fair comparison across episodes that aired on different dates

## Limitations

- **Not comprehensive**: Only tracks torrents on Nyaa.si, not streaming or direct downloads
- **Biased sample**: Nyaa is primarily used by international fans; Japanese domestic viewership is not captured
- **Delayed data**: Statistics lag by ~24 hours due to scrape frequency
- **Aggregation assumptions**: Summing torrents may over/under-count if viewers download multiple versions

## Technology Stack

- **Backend**: Python 3.11+ with SQLite
- **ETL**: Polars, DuckDB, Pyarrow
- **Frontend**: Observable Framework, Observable Plot, Arquero
- **Deployment**: Static hosting (Vercel/Cloudflare Pages)

## Source Code

This project is open source: [github.com/hiinaspace/nyaastats](https://github.com/hiinaspace/nyaastats)

## License

This project is licensed under the [WTFPL](http://www.wtfpl.net/).

Data is provided as-is for educational and entertainment purposes. Nyaa.si data is publicly available; AniList data is used under their API terms.

---

<div class="note">
  Questions or feedback? Open an issue on <a href="https://github.com/hiinaspace/nyaastats/issues">GitHub</a>.
</div>
