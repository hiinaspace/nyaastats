import logging
import sys
import time

import httpx

from .config import settings
from .database import Database
from .html_scraper import HtmlScraper

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def backfill(max_pages: int = 100) -> None:
    """Perform historical backfill from HTML browse pages."""
    db = Database(settings.db_path)

    # Create HTTP client with proper configuration
    client = httpx.Client(
        timeout=30.0,
        headers={"User-Agent": "nyaastats/1.0 Backfill Tool"},
        follow_redirects=True,
    )

    scraper = HtmlScraper(db, client)

    logger.info(f"Starting backfill for up to {max_pages} pages")
    logger.info(f"Base URL: {scraper.base_url}")
    logger.info(f"Database: {settings.db_path}")

    total_processed = 0

    try:
        for page in range(1, max_pages + 1):
            logger.info(f"Processing page {page}/{max_pages}")

            try:
                processed = scraper.process_page(page=page)
                total_processed += processed

                # Rate limit - be nice to the server
                time.sleep(5)

            except Exception as e:
                logger.error(f"Failed to process page {page}: {e}")
                # Continue with next page instead of breaking
                continue

        logger.info(f"Backfill complete. Total processed: {total_processed} torrents")

        # Show final metrics
        from .scheduler import Scheduler

        scheduler = Scheduler(db)
        metrics = scheduler.get_metrics()
        logger.info(f"Final metrics: {metrics}")

        schedule_summary = scheduler.get_schedule_summary()
        logger.info(f"Schedule summary: {schedule_summary}")

    finally:
        client.close()


def main() -> None:
    """Main entry point for backfill script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill historical torrent data from HTML browse pages"
    )
    parser.add_argument(
        "max_pages",
        type=int,
        nargs="?",
        default=100,
        help="Maximum number of HTML pages to process (default: 100)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=settings.db_path,
        help=f"Path to SQLite database (default: {settings.db_path})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=settings.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=f"Logging level (default: {settings.log_level})",
    )

    args = parser.parse_args()

    # Update settings with command line args
    settings.db_path = args.db_path
    settings.log_level = args.log_level

    # Reconfigure logging with new level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))

    try:
        backfill(args.max_pages)
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
