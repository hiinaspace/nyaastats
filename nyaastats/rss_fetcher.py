import json
import logging
from collections.abc import Callable
from urllib.parse import urlparse

import feedparser
import guessit
import httpx
from guessit.jsonutils import GuessitEncoder
from whenever import Instant

from .database import Database
from .models import TorrentData

logger = logging.getLogger(__name__)


class RSSFetcher:
    def __init__(
        self,
        db: Database,
        client: httpx.Client,
        feed_url: str = "https://nyaa.si/?page=rss&c=1_2&f=0",
        now_func: Callable[[], Instant] = Instant.now,
    ):
        self.db = db
        self.feed_url = feed_url
        self.client = client
        self.now_func = now_func

    def fetch_feed(self, page: int | None = None) -> feedparser.FeedParserDict:
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

    def parse_entry(self, entry: feedparser.FeedParserDict) -> TorrentData:
        """Parse RSS entry into torrent data with guessit metadata."""
        # Extract nyaa-specific fields from namespaced elements
        infohash = getattr(entry, "nyaa_infohash", "")
        if not infohash:
            # Try alternative attribute names in case namespace handling varies
            infohash = getattr(entry, "infohash", "")

        # Parse GUID for nyaa ID
        guid_url = urlparse(getattr(entry, "guid", ""))
        nyaa_id = None
        if guid_url.path:
            try:
                nyaa_id = int(guid_url.path.split("/")[-1])
            except (ValueError, IndexError):
                pass

        # Parse size (convert to bytes)
        size_str = getattr(entry, "nyaa_size", "0 B")
        if not size_str:
            size_str = "0 B"
        size_bytes = self._parse_size(size_str)

        # Parse dates - handle both RSS date formats
        pubdate_str = getattr(entry, "published", "")
        if pubdate_str:
            try:
                # Use feedparser's built-in date parsing
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    # published_parsed is a time.struct_time with at least 6 elements
                    parsed_time = entry.published_parsed
                    if len(parsed_time) >= 6:
                        pubdate = Instant.from_utc(
                            parsed_time[0],
                            parsed_time[1],
                            parsed_time[2],
                            parsed_time[3],
                            parsed_time[4],
                            parsed_time[5],
                        )
                    else:
                        pubdate = self.now_func()
                else:
                    # Fallback to manual parsing - feedparser should handle this
                    pubdate = self.now_func()
            except Exception as e:
                logger.warning(f"Failed to parse pubdate '{pubdate_str}': {e}")
                pubdate = self.now_func()
        else:
            pubdate = self.now_func()

        # Extract metadata with guessit
        filename = getattr(entry, "title", "")
        guessit_data = None
        if filename:
            try:
                guessit_result = guessit.guessit(filename)
                guessit_data = json.loads(
                    json.dumps(guessit_result, cls=GuessitEncoder, ensure_ascii=False)
                )
            except Exception as e:
                logger.warning(f"Guessit parsing failed for '{filename}': {e}")
                guessit_data = None

        torrent_data = TorrentData(
            infohash=infohash.lower(),
            filename=filename,
            pubdate=pubdate,
            size_bytes=size_bytes,
            nyaa_id=nyaa_id,
            trusted=getattr(entry, "nyaa_trusted", "No") == "Yes",
            remake=getattr(entry, "nyaa_remake", "No") == "Yes",
            seeders=int(getattr(entry, "nyaa_seeders", "0")),
            leechers=int(getattr(entry, "nyaa_leechers", "0")),
            downloads=int(getattr(entry, "nyaa_downloads", "0")),
            guessit_data=guessit_data,
        )

        # Mark as failed in database if guessit parsing failed and torrent exists
        if not guessit_data and self.db.get_torrent_exists(torrent_data.infohash):
            self.db.mark_torrent_status(torrent_data.infohash, "guessit_failed")

        return torrent_data

    def _parse_size(self, size_str: str) -> int:
        """Convert size string to bytes."""
        parts = size_str.split()
        if len(parts) != 2:
            return 0

        try:
            value = float(parts[0])
            unit = parts[1].upper()
        except (ValueError, IndexError):
            return 0

        multipliers = {
            "B": 1,
            "KB": 1024,
            "KIB": 1024,
            "MB": 1024**2,
            "MIB": 1024**2,
            "GB": 1024**3,
            "GIB": 1024**3,
            "TB": 1024**4,
            "TIB": 1024**4,
        }

        multiplier = multipliers.get(unit, 0)
        if multiplier == 0:
            return 0
        return int(value * multiplier)

    def process_feed(self, page: int | None = None) -> int:
        """Fetch and process RSS feed entries."""
        feed = self.fetch_feed(page)

        processed = 0
        for entry in feed.entries:
            try:
                torrent_data = self.parse_entry(entry)

                # Skip if we don't have essential data
                if not torrent_data.infohash or not torrent_data.filename:
                    logger.warning(
                        f"Skipping entry with missing infohash or filename: {entry.get('title', 'Unknown')}"
                    )
                    continue

                self.db.insert_torrent(torrent_data)
                processed += 1
            except Exception as e:
                logger.error(
                    f"Failed to process entry {entry.get('title', 'Unknown')}: {e}"
                )

        logger.info(f"Processed {processed} torrents from RSS feed")
        return processed
