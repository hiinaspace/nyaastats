import logging
from collections.abc import Callable

import bencodepy
import httpx
from whenever import Instant

from .database import Database
from .models import StatsData

logger = logging.getLogger(__name__)


class TrackerScraper:
    def __init__(
        self,
        db: Database,
        client: httpx.Client,
        tracker_url: str = "http://nyaa.tracker.wf:7777/scrape",
        now_func: Callable[[], Instant] = Instant.now,
    ):
        self.db = db
        self.tracker_url = tracker_url
        self.client = client
        self.now_func = now_func

    def scrape_batch(self, infohashes: list[str]) -> dict[str, StatsData]:
        """Scrape a batch of infohashes from the tracker."""
        if not infohashes:
            return {}

        # Build query string with URL-encoded infohashes
        params = []
        valid_infohashes = []
        for infohash in infohashes:
            try:
                # Validate infohash format (must be a valid hex string)
                # This also indirectly checks if it has an even number of characters
                bytes.fromhex(infohash)

                # Manual URI encoding: uppercase each hex octet and prepend with '%'
                # Example: "abcdef01" becomes "%AB%CD%EF%01"
                encoded = "".join(
                    f"%{infohash[i : i + 2].upper()}"
                    for i in range(0, len(infohash), 2)
                )

                params.append(f"info_hash={encoded}")
                valid_infohashes.append(infohash)
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
            # bencodepy.decode returns a dict, so this is safe
            files = data.get(b"files", {}) if isinstance(data, dict) else {}

            for info_hash_bytes, stats in files.items():
                infohash = info_hash_bytes.hex()
                results[infohash] = StatsData(
                    seeders=stats.get(b"complete", 0),
                    leechers=stats.get(b"incomplete", 0),
                    downloads=stats.get(b"downloaded", 0),
                )

            # Fill in zeros for any missing valid infohashes
            for infohash in valid_infohashes:
                if infohash not in results:
                    results[infohash] = StatsData(seeders=0, leechers=0, downloads=0)

            return results

        except Exception as e:
            logger.error(f"Tracker scrape failed: {e}")
            # Return zeros for all valid torrents
            # TODO don't return zero, total tracker failure shouldn't count for individual torrent missing
            return {
                ih: StatsData(seeders=0, leechers=0, downloads=0)
                for ih in valid_infohashes
            }

    def update_stats(
        self, infohash: str, stats: StatsData, timestamp: Instant | None = None
    ) -> None:
        """Update stats for a single infohash."""
        if timestamp is None:
            timestamp = self.now_func().round()

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

    def update_batch_stats(self, results: dict[str, StatsData]) -> None:
        """Update stats for a batch of torrents."""
        for infohash, stats in results.items():
            self.update_stats(infohash, stats)
