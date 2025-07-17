# Nyaa Torrent Tracker Statistics - Design Document

## Overview

This project tracks download, seed, and leech counts from the nyaa.si torrent tracker over time, providing market data for western anime viewership. The system periodically fetches new torrents via RSS, extracts metadata using guessit, and tracks statistics over time using a time-decay scraping algorithm.

## Architecture

### Components

1. **RSS Fetcher**: Discovers new torrents and performs historical backfill
2. **Metadata Parser**: Uses guessit to extract structured data from filenames
3. **Tracker Scraper**: Fetches current stats from BitTorrent HTTP scrape protocol
4. **Time-Decay Scheduler**: Determines which torrents to scrape based on age with batching windows
5. **Database**: SQLite with time-series stats and torrent metadata

### Execution Model

The system uses a **run-once model** executed via cron, rather than a long-running daemon:

1. **RSS Fetch**: Check if RSS should be fetched based on interval, process if needed
2. **Batch Scraping**: Query for torrents due within batching window, scrape in batches
3. **Statistics**: Print current metrics and schedule summary
4. **Exit**: Clean up resources and exit

### Data Flow

```
Cron Scheduler → RSS Feed → Parse XML → Extract Metadata → Store in DB
                                                  ↓
                              HTTP Scrape API ← Time-Decay Query (with batching window)
                                                  ↓
                                          Update Stats Table → Print Stats → Exit
```

## Data Model

### Tables

#### torrents
Primary table for torrent metadata
```sql
CREATE TABLE torrents (
    infohash TEXT PRIMARY KEY,          -- 40-char hex string
    filename TEXT NOT NULL,             -- Original filename from RSS
    pubdate TEXT NOT NULL,              -- ISO8601 Publication date from RSS
    size_bytes INTEGER,                 -- Size in bytes
    nyaa_id INTEGER,                    -- Nyaa torrent ID
    trusted BOOLEAN,                    -- Trusted uploader flag
    remake BOOLEAN,                     -- Remake flag
    status TEXT DEFAULT 'active',       -- 'active', 'dead', 'guessit_failed'

    -- Guessit metadata stored as JSON
    guessit_data TEXT                   -- JSON object containing all guessit fields
);
```

#### stats
Time-series table for tracker statistics
```sql
CREATE TABLE stats (
    infohash TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    seeders INTEGER NOT NULL,
    leechers INTEGER NOT NULL,
    downloads INTEGER NOT NULL,
    PRIMARY KEY (infohash, timestamp),
    FOREIGN KEY (infohash) REFERENCES torrents(infohash)
);

CREATE INDEX idx_stats_infohash ON stats(infohash);
CREATE INDEX idx_stats_timestamp ON stats(timestamp);
```

### Guessit Data Storage

The `guessit_data` column stores the complete output of guessit parsing as JSON. This approach:
- Leverages guessit's native JSON encoder (`GuessitEncoder`) to handle complex data types
- Eliminates validation errors from Language objects, episode lists, and other guessit types
- Provides flexibility to store any guessit output without schema changes
- Simplifies the codebase by removing custom type conversion logic

Example guessit_data JSON:
```json
{
  "title": "Test Anime",
  "season": 1,
  "episode": 1,
  "screen_size": "1080p",
  "video_codec": "H.264",
  "audio_codec": "AAC",
  "container": "mkv",
  "release_group": "TestGroup",
  "language": "en",
  "subtitles": ["en", "jp"],
  "type": "episode"
}
```

### SQLite Configuration
- Enable WAL mode for concurrent reads during operation
- Use `PRAGMA synchronous = NORMAL` for better write performance
- Regular `VACUUM` operations to maintain performance

## Core Algorithms

### Time-Decay Scraping Schedule

Torrents are scraped at decreasing frequency based on age:
- **First 48 hours**: Every hour
- **Days 3-7**: Every 4 hours
- **Week 2-4**: Every day
- **Month 2-6**: Every week
- **After 6 months**: Never (unless manually reset)

### Batching Window Optimization

To improve efficiency, the scheduler includes a configurable batching window (default: 30 minutes) that allows scraping torrents that will be due within the window, rather than waiting for their exact due time. This batching approach:

- Reduces total number of scrape requests
- Improves tracker resource utilization
- Has minimal impact on data quality given the hour/day/week cadence
- Allows for more efficient batch processing

#### SQL Query for Due Torrents
```sql
SELECT t.infohash
FROM torrents t
LEFT JOIN (
    SELECT infohash, MAX(timestamp) as last_scrape
    FROM stats
    GROUP BY infohash
) s ON t.infohash = s.infohash
WHERE t.status = 'active'
  AND (
    -- Never scraped (only RSS stats)
    s.last_scrape IS NULL
    OR
    -- Time-based rules
    CASE
      WHEN (julianday('now') - julianday(t.pubdate)) <= 2 THEN
        -- First 48 hours: hourly
        (julianday('now') - julianday(s.last_scrape)) * 24 >= 1
      WHEN (julianday('now') - julianday(t.pubdate)) <= 7 THEN
        -- Days 3-7: every 4 hours
        (julianday('now') - julianday(s.last_scrape)) * 24 >= 4
      WHEN (julianday('now') - julianday(t.pubdate)) <= 30 THEN
        -- Week 2-4: daily
        (julianday('now') - julianday(s.last_scrape)) >= 1
      WHEN (julianday('now') - julianday(t.pubdate)) <= 180 THEN
        -- Month 2-6: weekly
        (julianday('now') - julianday(s.last_scrape)) >= 7
      ELSE
        -- After 6 months: never
        FALSE
    END
  )
ORDER BY s.last_scrape ASC NULLS FIRST
LIMIT ?;
```

### Dead Torrent Detection

Torrents are marked dead after 3 consecutive scrapes returning zero for all metrics:
```sql
-- Check if torrent should be marked dead
WITH recent_stats AS (
    SELECT seeders, leechers, downloads
    FROM stats
    WHERE infohash = ?
    ORDER BY timestamp DESC
    LIMIT 3
)
SELECT COUNT(*) = 3
   AND SUM(seeders + leechers + downloads) = 0
FROM recent_stats;
```

### Tracker Scrape Protocol

HTTP scrape requests follow BEP 48:
```
GET http://nyaa.tracker.wf:7777/scrape?info_hash=%91%4E%5C%88...
```

Response is bencoded dictionary containing:
```
{
  'files': {
    '<20-byte-infohash>': {
      'complete': seeders,
      'incomplete': leechers,
      'downloaded': downloads
    }
  }
}
```

Multiple info_hash parameters can be included (tested limit ~40).

## Operational Considerations

### Cron-Based Execution
The system is designed to run via cron scheduler:
```bash
# Run every hour
0 * * * * cd /path/to/nyaastats && uv run nyaastats

# Or run every 30 minutes for more frequent updates
*/30 * * * * cd /path/to/nyaastats && uv run nyaastats
```

### Rate Limiting
- RSS fetch: Once per hour (configurable)
- Tracker scrape: No artificial rate limiting (runs only when scheduled)
- Batch size: ~20 infohashes per scrape request (configurable)
- Batching window: 30 minutes ahead to improve batch efficiency

### Error Handling
- Network failures: Exponential backoff with max 5 retries
- Malformed RSS: Log and skip entry
- Guessit failures: Mark as 'guessit_failed' status
- Tracker errors: Treat as 0/0/0 response
- Process failures: Cron handles restart/retry logic

### Monitoring Metrics
- `torrents.total`: Total torrents tracked
- `torrents.active`: Active torrents (not dead)
- `scrapes.success_rate`: Successful scrape percentage
- `scrapes.queue_depth`: Torrents pending scrape
- `rss.last_success`: Time since last RSS fetch
- `tracker.response_time`: Average scrape response time

### Monitoring Integration
- **Cron logs**: Monitor cron execution success/failure
- **Application logs**: Structured logging for each execution
- **Resource efficiency**: Only uses CPU/memory when actually working
- **Fault tolerance**: Each execution is independent, failures don't affect future runs

### Data Retention
No automatic retention policy - data grows at approximately:
- ~100 torrents/day × 365 days = 36,500 torrents/year
- ~50 stat points/torrent × 36,500 = 1.8M rows/year
- Estimated size: <1GB/year

## Configuration

### Environment Variables
All configuration can be set via environment variables with `NYAA_` prefix:

- `NYAA_RSS_FETCH_INTERVAL_HOURS` (default: 1): RSS fetch interval
- `NYAA_SCRAPE_BATCH_SIZE` (default: 20): Torrents per batch
- `NYAA_SCRAPE_WINDOW_MINUTES` (default: 30): Batching window for due torrents
- `NYAA_LOG_LEVEL` (default: INFO): Logging verbosity
- `NYAA_DB_PATH` (default: nyaastats.db): Database file path

### Cron Configuration Examples
```bash
# Basic hourly execution
0 * * * * cd /path/to/nyaastats && uv run nyaastats

# More frequent execution (every 30 minutes)
*/30 * * * * cd /path/to/nyaastats && uv run nyaastats

# With custom environment variables
0 * * * * cd /path/to/nyaastats && NYAA_SCRAPE_WINDOW_MINUTES=60 uv run nyaastats

# With logging to file
0 * * * * cd /path/to/nyaastats && uv run nyaastats >> /var/log/nyaastats.log 2>&1
```

## Future Considerations

### Potential Extensions
- Support for additional nyaa categories (non-English, etc)
- Integration with external anime databases (MAL, AniList)
- Advanced torrent grouping/deduplication

### Data Analysis Opportunities
- Seasonal viewing patterns
- Release group popularity
- First-24-hour velocity as popularity metric
- Correlation with official streaming releases
- Long-tail distribution of older content
