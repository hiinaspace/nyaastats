import logging
import sys
from collections.abc import Callable

import httpx
from whenever import Instant, hours

from .config import settings
from .database import Database
from .rss_fetcher import RSSFetcher
from .scheduler import Scheduler
from .tracker import TrackerScraper

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class NyaaTracker:
    """Main coordinator class for run-once execution."""

    def __init__(self, now_func: Callable[[], Instant] = Instant.now):
        self.now_func = now_func
        self.db = Database(settings.db_path, now_func)

        # Create HTTP clients with proper configuration
        self.rss_client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "nyaastats/1.0 RSS Fetcher"},
            follow_redirects=True,
        )
        self.tracker_client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "nyaastats/1.0 Tracker Scraper"},
        )

        self.rss_fetcher = RSSFetcher(
            self.db, self.rss_client, settings.rss_url, now_func
        )
        self.tracker = TrackerScraper(
            self.db, self.tracker_client, settings.tracker_url, now_func
        )
        self.scheduler = Scheduler(self.db, settings.scrape_batch_size, now_func)
        self.rss_fetch_interval_hours = settings.rss_fetch_interval_hours

    def run(self) -> None:
        """Run once execution: RSS → Scrape → Stats → Exit."""
        logger.info("Starting Nyaa tracker run")
        logger.info(f"RSS URL: {settings.rss_url}")
        logger.info(f"Tracker URL: {settings.tracker_url}")
        logger.info(f"Database: {settings.db_path}")
        logger.info(f"Scrape batch size: {settings.scrape_batch_size}")
        logger.info(f"RSS fetch interval: {settings.rss_fetch_interval_hours} hours")
        logger.info(f"Scrape window: {settings.scrape_window_minutes} minutes")

        try:
            # 1. Fetch RSS if needed
            if self._should_fetch_rss():
                logger.info("Fetching RSS feed")
                try:
                    processed = self.rss_fetcher.process_feed()
                    logger.info(f"RSS fetch completed, processed {processed} entries")
                except Exception as e:
                    logger.error(f"RSS fetch failed: {e}")
            else:
                logger.info("RSS fetch not needed")

            # 2. Scrape due torrents with batching window
            due_torrents = self.scheduler.get_due_torrents_with_window(
                settings.scrape_window_minutes
            )

            if due_torrents:
                logger.info(f"Scraping {len(due_torrents)} torrents")
                try:
                    # Scrape in batches
                    results = self.tracker.scrape_batch(due_torrents)
                    # Update stats
                    self.tracker.update_batch_stats(results)
                    logger.info(f"Scrape completed for {len(results)} torrents")
                except Exception as e:
                    logger.error(f"Scraping failed: {e}")
            else:
                logger.info("No torrents due for scraping")

            # 3. Print current stats
            self.print_stats()

        except Exception as e:
            logger.error(f"Error in run: {e}", exc_info=True)
            raise
        finally:
            self._cleanup()

        logger.info("Nyaa tracker run completed")

    def print_stats(self) -> None:
        """Print current system metrics and schedule summary."""
        try:
            metrics = self.scheduler.get_metrics()
            logger.info(f"Metrics: {metrics}")

            schedule_summary = self.scheduler.get_schedule_summary()
            logger.info(f"Schedule summary: {schedule_summary}")
        except Exception as e:
            logger.error(f"Failed to retrieve metrics: {e}")

    def _should_fetch_rss(self) -> bool:
        """Check if RSS should be fetched based on last fetch time in database."""
        # Get last RSS fetch time from database
        with self.db.get_conn() as conn:
            cursor = conn.execute("SELECT MAX(pubdate) as last_rss FROM torrents")
            row = cursor.fetchone()
            if not row or not row["last_rss"]:
                return True

            last_fetch = Instant.parse_common_iso(row["last_rss"])
            time_since_last = self.now_func() - last_fetch
            interval_duration = hours(self.rss_fetch_interval_hours)
            return time_since_last >= interval_duration

    def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            self.rss_client.close()
            self.tracker_client.close()
            self.db.vacuum()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def status(self) -> dict:
        """Get current system status."""
        # Get last RSS fetch time from database
        with self.db.get_conn() as conn:
            cursor = conn.execute("SELECT MAX(pubdate) as last_rss FROM torrents")
            row = cursor.fetchone()
            last_rss_fetch = row["last_rss"] if row else None

        return {
            "last_rss_fetch": last_rss_fetch,
            "next_rss_fetch": (
                Instant.parse_common_iso(last_rss_fetch).add(
                    hours=self.rss_fetch_interval_hours
                )
            ).format_common_iso()
            if last_rss_fetch
            else None,
            "metrics": self.scheduler.get_metrics(),
            "schedule_summary": self.scheduler.get_schedule_summary(),
        }


def main() -> None:
    """Main entry point."""
    try:
        tracker = NyaaTracker()
        tracker.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
