import logging
import signal
import sys
import time
from datetime import datetime, timedelta

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
    """Main daemon class that coordinates all components."""

    def __init__(self):
        self.db = Database(settings.db_path)
        self.rss_fetcher = RSSFetcher(self.db, settings.rss_url)
        self.tracker = TrackerScraper(self.db, settings.tracker_url)
        self.scheduler = Scheduler(self.db, settings.scrape_batch_size)
        self.running = True

        # Track last RSS fetch
        self.last_rss_fetch: datetime | None = None
        self.rss_fetch_interval = timedelta(hours=settings.rss_fetch_interval_hours)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Shutdown signal received (signal {signum})")
        self.running = False

    def run(self) -> None:
        """Main daemon loop."""
        logger.info("Starting Nyaa tracker daemon")
        logger.info(f"RSS URL: {settings.rss_url}")
        logger.info(f"Tracker URL: {settings.tracker_url}")
        logger.info(f"Database: {settings.db_path}")
        logger.info(f"Scrape batch size: {settings.scrape_batch_size}")
        logger.info(f"RSS fetch interval: {settings.rss_fetch_interval_hours} hours")
        logger.info(f"Scrape interval: {settings.scrape_interval_seconds} seconds")

        while self.running:
            try:
                loop_start = time.time()

                # Fetch RSS if needed
                if self._should_fetch_rss():
                    logger.info("Fetching RSS feed")
                    try:
                        processed = self.rss_fetcher.process_feed()
                        self.last_rss_fetch = datetime.utcnow()
                        logger.info(
                            f"RSS fetch completed, processed {processed} entries"
                        )
                    except Exception as e:
                        logger.error(f"RSS fetch failed: {e}")

                # Get torrents due for scraping
                due_torrents = self.scheduler.get_due_torrents()

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

                # Log metrics
                try:
                    metrics = self.scheduler.get_metrics()
                    logger.info(f"Metrics: {metrics}")

                    # Log schedule summary periodically
                    if int(time.time()) % 300 == 0:  # Every 5 minutes
                        schedule_summary = self.scheduler.get_schedule_summary()
                        logger.info(f"Schedule summary: {schedule_summary}")

                except Exception as e:
                    logger.error(f"Failed to retrieve metrics: {e}")

                # Calculate sleep time to maintain consistent intervals
                loop_duration = time.time() - loop_start
                sleep_time = max(0, settings.scrape_interval_seconds - loop_duration)

                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(settings.scrape_interval_seconds)  # Continue after error

        logger.info("Shutting down daemon")
        self._cleanup()

    def _should_fetch_rss(self) -> bool:
        """Check if RSS should be fetched."""
        if self.last_rss_fetch is None:
            return True

        return datetime.utcnow() - self.last_rss_fetch > self.rss_fetch_interval

    def _cleanup(self) -> None:
        """Clean up resources."""
        try:
            self.rss_fetcher.close()
            self.tracker.close()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def status(self) -> dict:
        """Get current daemon status."""
        return {
            "running": self.running,
            "last_rss_fetch": self.last_rss_fetch.isoformat()
            if self.last_rss_fetch
            else None,
            "next_rss_fetch": (
                self.last_rss_fetch + self.rss_fetch_interval
            ).isoformat()
            if self.last_rss_fetch
            else None,
            "metrics": self.scheduler.get_metrics(),
            "schedule_summary": self.scheduler.get_schedule_summary(),
        }


def main() -> None:
    """Main entry point."""
    try:
        tracker = NyaaTracker()
        tracker.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
