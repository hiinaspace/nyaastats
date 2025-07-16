# Nyaa Torrent Tracker Statistics - Design Document

## Overview

This project tracks download, seed, and leech counts from the nyaa.si torrent tracker over time, providing market data for western anime viewership. The system periodically fetches new torrents via RSS, extracts metadata using guessit, and tracks statistics over time using a time-decay scraping algorithm.

## Architecture

### Components

1. **RSS Fetcher**: Discovers new torrents and performs historical backfill
2. **Metadata Parser**: Uses guessit to extract structured data from filenames
3. **Tracker Scraper**: Fetches current stats from BitTorrent HTTP scrape protocol
4. **Time-Decay Scheduler**: Determines which torrents to scrape based on age
5. **Database**: SQLite with time-series stats and torrent metadata

### Data Flow

```
RSS Feed → Parse XML → Extract Metadata → Store in DB
                            ↓
                    HTTP Scrape API ← Time-Decay Query
                            ↓
                    Update Stats Table
```

## Data Model

### Tables

#### torrents
Primary table for torrent metadata
```sql
CREATE TABLE torrents (
    infohash TEXT PRIMARY KEY,          -- 40-char hex string
    filename TEXT NOT NULL,             -- Original filename from RSS
    pubdate TIMESTAMP NOT NULL,         -- Publication date from RSS
    size_bytes INTEGER,                 -- Size in bytes
    nyaa_id INTEGER,                    -- Nyaa torrent ID
    trusted BOOLEAN,                    -- Trusted uploader flag
    remake BOOLEAN,                     -- Remake flag
    status TEXT DEFAULT 'active',       -- 'active', 'dead', 'guessit_failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Guessit extracted fields (nullable)
    title TEXT,
    alternative_title TEXT,
    episode INTEGER,
    season INTEGER,
    year INTEGER,
    release_group TEXT,
    resolution TEXT,                    -- '1080p', '720p', etc
    video_codec TEXT,                   -- 'x265', 'x264', etc
    audio_codec TEXT,                   -- 'AAC', 'FLAC', etc
    source TEXT,                        -- 'Web', 'BluRay', etc
    container TEXT,                     -- 'mkv', 'mp4', etc
    language TEXT,
    subtitles TEXT,                     -- JSON array of subtitle languages
    other TEXT                          -- JSON object for other guessit fields
);
```

#### stats
Time-series table for tracker statistics
```sql
CREATE TABLE stats (
    infohash TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    seeders INTEGER NOT NULL,
    leechers INTEGER NOT NULL,
    downloads INTEGER NOT NULL,
    PRIMARY KEY (infohash, timestamp),
    FOREIGN KEY (infohash) REFERENCES torrents(infohash)
);

CREATE INDEX idx_stats_infohash ON stats(infohash);
CREATE INDEX idx_stats_timestamp ON stats(timestamp);
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

### Rate Limiting
- RSS fetch: Once per hour
- Tracker scrape: Maximum 1 request per minute
- Batch size: ~40 infohashes per scrape request

### Error Handling
- Network failures: Exponential backoff with max 5 retries
- Malformed RSS: Log and skip entry
- Guessit failures: Mark as 'guessit_failed' status
- Tracker errors: Treat as 0/0/0 response

### Monitoring Metrics
- `torrents.total`: Total torrents tracked
- `torrents.active`: Active torrents (not dead)
- `scrapes.success_rate`: Successful scrape percentage
- `scrapes.queue_depth`: Torrents pending scrape
- `rss.last_success`: Time since last RSS fetch
- `tracker.response_time`: Average scrape response time

### Data Retention
No automatic retention policy - data grows at approximately:
- ~100 torrents/day × 365 days = 36,500 torrents/year
- ~50 stat points/torrent × 36,500 = 1.8M rows/year
- Estimated size: <1GB/year

## Future Considerations

### Potential Extensionstrs
- Support for additional nyaa categories (non-English, etc)
- Integration with external anime databases (MAL, AniList)
- Advanced torrent grouping/deduplication

### Data Analysis Opportunities
- Seasonal viewing patterns
- Release group popularity
- First-24-hour velocity as popularity metric
- Correlation with official streaming releases
- Long-tail distribution of older content
