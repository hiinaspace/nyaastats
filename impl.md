# Nyaa Torrent Tracker - Implementation Guide

## Project Setup

### Directory Structure
```
nyaastats/
├── nyaastats/
│   ├── __init__.py
│   ├── database.py      # Database connection and schema
│   ├── rss_fetcher.py   # RSS feed parsing
│   ├── tracker.py       # BitTorrent scrape protocol
│   ├── scheduler.py     # Time-decay scheduling
│   ├── main.py          # Main daemon loop
│   └── backfill.py      # One-time historical backfill
├── tests/
├── pyproject.toml
├── README.md
├── config.py
```

### Dependencies

use uv to manage dependencies, so `uv add` to update pyproject.toml

```txt
httpx>=0.24.0           # Modern HTTP client
feedparser>=6.0.0       # RSS parsing
guessit>=3.7.0          # Filename metadata extraction
bencodepy>=0.9.5        # Bencode format for tracker response
pydantic>=2.0.0         # Config validation
logfire>=0.30.0         # Observability (optional initially)
whenever # Date parsing utilities
```

## Implementation Steps

### Step 1: Database Setup

**File: `database.py`**
```python
import sqlite3
from contextlib import contextmanager
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

SCHEMA = """
-- Enable WAL mode for concurrent access
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS torrents (
    infohash TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    pubdate TIMESTAMP NOT NULL,
    size_bytes INTEGER,
    nyaa_id INTEGER,
    trusted BOOLEAN DEFAULT 0,
    remake BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Guessit fields
    title TEXT,
    alternative_title TEXT,
    episode INTEGER,
    season INTEGER,
    year INTEGER,
    release_group TEXT,
    resolution TEXT,
    video_codec TEXT,
    audio_codec TEXT,
    source TEXT,
    container TEXT,
    language TEXT,
    subtitles TEXT,
    other TEXT
);

CREATE TABLE IF NOT EXISTS stats (
    infohash TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    seeders INTEGER NOT NULL,
    leechers INTEGER NOT NULL,
    downloads INTEGER NOT NULL,
    PRIMARY KEY (infohash, timestamp),
    FOREIGN KEY (infohash) REFERENCES torrents(infohash)
);

CREATE INDEX IF NOT EXISTS idx_stats_infohash ON stats(infohash);
CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_torrents_pubdate ON torrents(pubdate);
CREATE INDEX IF NOT EXISTS idx_torrents_status ON torrents(status);
"""

class Database:
    def __init__(self, db_path="nyaastats.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with self.get_conn() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert_torrent(self, torrent_data, guessit_datrequirementsa):
        with self.get_conn() as conn:
            # Insert torrent metadata
            conn.execute("""
                INSERT OR IGNORE INTO torrents (
                    infohash, filename, pubdate, size_bytes, nyaa_id,
                    trusted, remake, title, episode, season, year,
                    release_group, resolution, video_codec, audio_codec,
                    source, container, language, subtitles, other
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                torrent_data['infohash'],
                torrent_data['filename'],
                torrent_data['pubdate'],
                torrent_data['size_bytes'],
                torrent_data['nyaa_id'],
                torrent_data['trusted'],
                torrent_data['remake'],
                guessit_data.get('title'),
                guessit_data.get('episode'),
                guessit_data.get('season'),
                guessit_data.get('year'),
                guessit_data.get('release_group'),
                guessit_data.get('resolution'),
                guessit_data.get('video_codec'),
                guessit_data.get('audio_codec'),
                guessit_data.get('source'),
                guessit_data.get('container'),
                guessit_data.get('language'),
                json.dumps(guessit_data.get('subtitles', [])),
                json.dumps({k: v for k, v in guessit_data.items()
                           if k not in ['title', 'episode', 'season', 'year',
                                       'release_group', 'resolution', 'video_codec',
                                       'audio_codec', 'source', 'container',
                                       'language', 'subtitles']})
            ))

            # Insert initial stats from RSS
            conn.execute("""
                INSERT INTO stats (infohash, timestamp, seeders, leechers, downloads)
                VALUES (?, ?, ?, ?, ?)
            """, (
                torrent_data['infohash'],
                torrent_data['pubdate'],
                torrent_data['seeders'],
                torrent_data['leechers'],
                torrent_data['downloads']
            ))

            conn.commit()
```

### Step 2: RSS Fetcher

**File: `rss_fetcher.py`**
```python
import feedparser
import httpx
from datetime import datetime
import logging
from urllib.parse import parse_qs, urlparse
import guessit
import json

logger = logging.getLogger(__name__)

class RSSFetcher:
    def __init__(self, db, feed_url="https://nyaa.si/?page=rss&c=1_2&f=0"):
        self.db = db
        self.feed_url = feed_url
        self.client = httpx.Client(timeout=30.0)

    def fetch_feed(self, page=None):
        """Fetch RSS feed, optionally with pagination."""
        url = self.feed_url
        if page:
            url += f"&p={page}"

        try:
            response = self.client.get(url)
            response.raise_for_status()
            return feedparser.parse(response.text)
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed: {e}")
            raise

    def parse_entry(self, entry):
        """Parse RSS entry into torrent data."""
        # Extract nyaa-specific fields
        nyaa_ns = entry.get('nyaa_infohash', '')

        # Parse GUID for nyaa ID
        guid_url = urlparse(entry.get('guid', ''))
        nyaa_id = int(guid_url.path.split('/')[-1]) if guid_url.path else None

        # Parse size (convert to bytes)
        size_str = entry.get('nyaa_size', '0 B')
        size_bytes = self._parse_size(size_str)

        # Parse dates
        pubdate = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %z')

        torrent_data = {
            'infohash': entry.get('nyaa_infohash', '').lower(),
            'filename': entry.title,
            'pubdate': pubdate,
            'size_bytes': size_bytes,
            'nyaa_id': nyaa_id,
            'trusted': entry.get('nyaa_trusted', 'No') == 'Yes',
            'remake': entry.get('nyaa_remake', 'No') == 'Yes',
            'seeders': int(entry.get('nyaa_seeders', 0)),
            'leechers': int(entry.get('nyaa_leechers', 0)),
            'downloads': int(entry.get('nyaa_downloads', 0))
        }

        # Extract metadata with guessit
        try:
            guessit_data = guessit.guessit(entry.title)
            # Convert Path objects to strings
            for key, value in guessit_data.items():
                if hasattr(value, '__fspath__'):
                    guessit_data[key] = str(value)
        except Exception as e:
            logger.warning(f"Guessit failed for {entry.title}: {e}")
            guessit_data = {}
            # Mark as failed in database
            with self.db.get_conn() as conn:
                conn.execute(
                    "UPDATE torrents SET status = 'guessit_failed' WHERE infohash = ?",
                    (torrent_data['infohash'],)
                )

        return torrent_data, guessit_data

    def _parse_size(self, size_str):
        """Convert size string to bytes."""
        parts = size_str.split()
        if len(parts) != 2:
            return 0

        value = float(parts[0])
        unit = parts[1].upper()

        multipliers = {
            'B': 1,
            'KB': 1024,
            'KIB': 1024,
            'MB': 1024**2,
            'MIB': 1024**2,
            'GB': 1024**3,
            'GIB': 1024**3,
            'TB': 1024**4,
            'TIB': 1024**4,
        }

        return int(value * multipliers.get(unit, 1))

    def process_feed(self, page=None):
        """Fetch and process RSS feed entries."""
        feed = self.fetch_feed(page)

        processed = 0
        for entry in feed.entries:
            try:
                torrent_data, guessit_data = self.parse_entry(entry)
                self.db.insert_torrent(torrent_data, guessit_data)
                processed += 1
            except Exception as e:
                logger.error(f"Failed to process entry {entry.get('title', 'Unknown')}: {e}")

        logger.info(f"Processed {processed} torrents from RSS feed")
        return processed
```

### Step 3: Tracker Scraper

**File: `tracker.py`**
```python
import httpx
import bencodepy
from urllib.parse import quote
import logging
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class TrackerScraper:
    def __init__(self, db, tracker_url="http://nyaa.tracker.wf:7777/scrape"):
        self.db = db
        self.tracker_url = tracker_url
        self.client = httpx.Client(timeout=30.0)

    def scrape_batch(self, infohashes):
        """Scrape a batch of infohashes from the tracker."""
        if not infohashes:
            return {}

        # Build query string with URL-encoded infohashes
        params = []
        for infohash in infohashes:
            # Convert hex to bytes then URL encode
            info_hash_bytes = bytes.fromhex(infohash)
            encoded = quote(info_hash_bytes, safe='')
            params.append(f"info_hash={encoded}")

        query_string = "&".join(params)
        url = f"{self.tracker_url}?{query_string}"

        try:
            response = self.client.get(url)
            response.raise_for_status()

            # Decode bencode response
            data = bencodepy.decode(response.content)

            results = {}
            files = data.get(b'files', {})

            for info_hash_bytes, stats in files.items():
                infohash = info_hash_bytes.hex()
                results[infohash] = {
                    'seeders': stats.get(b'complete', 0),
                    'leechers': stats.get(b'incomplete', 0),
                    'downloads': stats.get(b'downloaded', 0)
                }

            return results

        except Exception as e:
            logger.error(f"Tracker scrape failed: {e}")
            # Return zeros for all requested torrents
            return {ih: {'seeders': 0, 'leechers': 0, 'downloads': 0}
                   for ih in infohashes}

    def update_stats(self, infohash, stats):
        """Update stats for a single infohash."""
        timestamp = datetime.utcnow()

        with self.db.get_conn() as conn:
            conn.execute("""
                INSERT INTO stats (infohash, timestamp, seeders, leechers, downloads)
                VALUES (?, ?, ?, ?, ?)
            """, (
                infohash,
                timestamp,
                stats['seeders'],
                stats['leechers'],
                stats['downloads']
            ))

            # Check if torrent should be marked dead
            if self._should_mark_dead(conn, infohash):
                conn.execute(
                    "UPDATE torrents SET status = 'dead' WHERE infohash = ?",
                    (infohash,)
                )
                logger.info(f"Marked torrent {infohash} as dead")

            conn.commit()

    def _should_mark_dead(self, conn, infohash):
        """Check if torrent has 3 consecutive zero responses."""
        cursor = conn.execute("""
            SELECT seeders, leechers, downloads
            FROM stats
            WHERE infohash = ?
            ORDER BY timestamp DESC
            LIMIT 3
        """, (infohash,))

        rows = cursor.fetchall()
        if len(rows) < 3:
            return False

        # Check if all 3 recent scrapes returned zeros
        return all(row['seeders'] == 0 and
                  row['leechers'] == 0 and
                  row['downloads'] == 0
                  for row in rows)
```

### Step 4: Scheduler

**File: `scheduler.py`**
```python
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Scheduler:
    def __init__(self, db, batch_size=40):
        self.db = db
        self.batch_size = batch_size

    def get_due_torrents(self):
        """Get torrents that are due for scraping based on time-decay algorithm."""
        with self.db.get_conn() as conn:
            cursor = conn.execute("""
                SELECT t.infohash
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                WHERE t.status = 'active'
                  AND (
                    s.last_scrape IS NULL
                    OR
                    CASE
                      WHEN (julianday('now') - julianday(t.pubdate)) <= 2 THEN
                        (julianday('now') - julianday(s.last_scrape)) * 24 >= 1
                      WHEN (julianday('now') - julianday(t.pubdate)) <= 7 THEN
                        (julianday('now') - julianday(s.last_scrape)) * 24 >= 4
                      WHEN (julianday('now') - julianday(t.pubdate)) <= 30 THEN
                        (julianday('now') - julianday(s.last_scrape)) >= 1
                      WHEN (julianday('now') - julianday(t.pubdate)) <= 180 THEN
                        (julianday('now') - julianday(s.last_scrape)) >= 7
                      ELSE
                        FALSE
                    END
                  )
                ORDER BY s.last_scrape ASC NULLS FIRST
                LIMIT ?
            """, (self.batch_size,))

            return [row['infohash'] for row in cursor]

    def get_metrics(self):
        """Get current system metrics."""
        with self.db.get_conn() as conn:
            metrics = {}

            # Total torrents
            cursor = conn.execute("SELECT COUNT(*) as count FROM torrents")
            metrics['torrents_total'] = cursor.fetchone()['count']

            # Active torrents
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM torrents WHERE status = 'active'"
            )
            metrics['torrents_active'] = cursor.fetchone()['count']

            # Queue depth (torrents due for scraping)
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                WHERE t.status = 'active'
                  AND (s.last_scrape IS NULL OR
                       julianday('now') - julianday(s.last_scrape) > 0.04)
            """)
            metrics['queue_depth'] = cursor.fetchone()['count']

            return metrics
```

### Step 5: Main Daemon

**File: `main.py`**
```python
import logging
import time
from datetime import datetime, timedelta
import signal
import sys

from database import Database
from rss_fetcher import RSSFetcher
from tracker import TrackerScraper
from scheduler import Scheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NyaaTracker:
    def __init__(self):
        self.db = Database()
        self.rss_fetcher = RSSFetcher(self.db)
        self.tracker = TrackerScraper(self.db)
        self.scheduler = Scheduler(self.db)
        self.running = True

        # Track last RSS fetch
        self.last_rss_fetch = None
        self.rss_fetch_interval = timedelta(hours=1)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False

    def run(self):
        """Main daemon loop."""
        logger.info("Starting Nyaa tracker daemon")

        while self.running:
            try:
                # Fetch RSS if needed
                if (self.last_rss_fetch is None or
                    datetime.utcnow() - self.last_rss_fetch > self.rss_fetch_interval):
                    logger.info("Fetching RSS feed")
                    self.rss_fetcher.process_feed()
                    self.last_rss_fetch = datetime.utcnow()

                # Get torrents due for scraping
                due_torrents = self.scheduler.get_due_torrents()

                if due_torrents:
                    logger.info(f"Scraping {len(due_torrents)} torrents")

                    # Scrape in batches
                    results = self.tracker.scrape_batch(due_torrents)

                    # Update stats
                    for infohash, stats in results.items():
                        self.tracker.update_stats(infohash, stats)

                    # Log metrics
                    metrics = self.scheduler.get_metrics()
                    logger.info(f"Metrics: {metrics}")

                # Sleep for 60 seconds
                time.sleep(60)

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(60)  # Continue after error

        logger.info("Daemon shutdown complete")

if __name__ == "__main__":
    tracker = NyaaTracker()
    tracker.run()
```

### Step 6: Backfill Script

**File: `backfill.py`**
```python
import logging
import time
from database import Database
from rss_fetcher import RSSFetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def backfill(max_pages=100):
    """Perform historical backfill from RSS feed."""
    db = Database()
    fetcher = RSSFetcher(db)

    logger.info(f"Starting backfill for up to {max_pages} pages")

    for page in range(1, max_pages + 1):
        logger.info(f"Processing page {page}/{max_pages}")

        try:
            processed = fetcher.process_feed(page=page)

            if processed == 0:
                logger.info("No more entries found, backfill complete")
                break

            # Rate limit - be nice to the server
            time.sleep(2)

        except Exception as e:
            logger.error(f"Failed to process page {page}: {e}")
            break

    logger.info("Backfill complete")

if __name__ == "__main__":
    import sys
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    backfill(max_pages)
```

### Step 7: Configuration

**File: `config.py`**
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Database
    db_path: str = "nyaastats.db"

    # RSS
    rss_url: str = "https://nyaa.si/?page=rss&c=1_2&f=0"
    rss_fetch_interval_hours: int = 1

    # Tracker
    tracker_url: str = "http://nyaa.tracker.wf:7777/scrape"
    scrape_batch_size: int = 40
    scrape_interval_seconds: int = 60

    # Logging
    log_level: str = "INFO"

    # Optional Logfire/OTEL
    enable_logfire: bool = False
    logfire_token: str = ""

    class Config:
        env_prefix = "NYAA_"

settings = Settings()
```

## Testing Strategy

### Unit Tests
1. **Database operations**: Test schema creation, insertions, queries
2. **RSS parsing**: Test entry parsing, size conversion, error handling
3. **Tracker protocol**: Mock bencode responses, test batch building
4. **Scheduler logic**: Test time-decay algorithm with various ages

### Integration Tests
1. **End-to-end RSS processing**: Use sample RSS XML
2. **Tracker scraping**: Use mock HTTP server
3. **Dead torrent detection**: Test state transitions

### Manual Testing
1. Run backfill on small page count
2. Monitor daemon for 24 hours
3. Verify stats accumulation
4. Check dead torrent marking

## Deployment

### Local Development
```bash
# set up venv
uv sync

# Run backfill
# TODO set up pyproject.toml defs for these scripts
uv run python -m nyaastats.backfill 10

# Run daemon
uv run python -m nyaastats.main
```
