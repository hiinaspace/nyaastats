import logging
from datetime import datetime
from urllib.parse import quote

import bencodepy
import httpx

from .database import Database

logger = logging.getLogger(__name__)


class TrackerScraper:
    def __init__(
        self, db: Database, tracker_url: str = "http://nyaa.tracker.wf:7777/scrape"
    ):
        self.db = db
        self.tracker_url = tracker_url
        self.client = httpx.Client(timeout=30.0)

    def scrape_batch(self, infohashes: list[str]) -> dict[str, dict[str, int]]:
        """Scrape a batch of infohashes from the tracker."""
        if not infohashes:
            return {}

        # Build query string with URL-encoded infohashes
        params = []
        for infohash in infohashes:
            try:
                # Convert hex to bytes then URL encode
                info_hash_bytes = bytes.fromhex(infohash)
                encoded = quote(info_hash_bytes, safe="")
                params.append(f"info_hash={encoded}")
            except ValueError as e:
                logger.warning(f"Invalid infohash format '{infohash}': {e}")
                continue

        if not params:
            return {}

        query_string = "&".join(params)
        url = f"{self.tracker_url}?{query_string}"

        try:
            response = self.client.get(url)
            response.raise_for_status()

            # Decode bencode response
            data = bencodepy.decode(response.content)

            results = {}
            files = data.get(b"files", {})

            for info_hash_bytes, stats in files.items():
                infohash = info_hash_bytes.hex()
                results[infohash] = {
                    "seeders": stats.get(b"complete", 0),
                    "leechers": stats.get(b"incomplete", 0),
                    "downloads": stats.get(b"downloaded", 0),
                }

            # Fill in zeros for any missing infohashes
            for infohash in infohashes:
                if infohash not in results:
                    results[infohash] = {"seeders": 0, "leechers": 0, "downloads": 0}

            return results

        except Exception as e:
            logger.error(f"Tracker scrape failed: {e}")
            # Return zeros for all requested torrents
            return {
                ih: {"seeders": 0, "leechers": 0, "downloads": 0} for ih in infohashes
            }

    def update_stats(self, infohash: str, stats: dict[str, int]) -> None:
        """Update stats for a single infohash."""
        timestamp = datetime.utcnow()

        # Insert the stats
        self.db.insert_stats(infohash, stats, timestamp)

        # Check if torrent should be marked dead
        if self._should_mark_dead(infohash):
            self.db.mark_torrent_status(infohash, "dead")
            logger.info(f"Marked torrent {infohash} as dead")

    def _should_mark_dead(self, infohash: str) -> bool:
        """Check if torrent has 3 consecutive zero responses."""
        recent_stats = self.db.get_recent_stats(infohash, limit=3)

        if len(recent_stats) < 3:
            return False

        # Check if all 3 recent scrapes returned zeros
        return all(
            row["seeders"] == 0 and row["leechers"] == 0 and row["downloads"] == 0
            for row in recent_stats
        )

    def update_batch_stats(self, results: dict[str, dict[str, int]]) -> None:
        """Update stats for a batch of torrents."""
        for infohash, stats in results.items():
            self.update_stats(infohash, stats)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
