import pytest

from nyaastats.database import Database
from nyaastats.rss_fetcher import RSSFetcher
from nyaastats.scheduler import Scheduler
from nyaastats.tracker import TrackerScraper


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db = Database(":memory:")
    yield db


@pytest.fixture
def rss_fetcher(temp_db):
    """Create RSS fetcher instance."""
    return RSSFetcher(temp_db)


@pytest.fixture
def tracker_scraper(temp_db):
    """Create tracker scraper instance."""
    return TrackerScraper(temp_db)


@pytest.fixture
def scheduler(temp_db):
    """Create scheduler instance."""
    return Scheduler(temp_db, batch_size=10)
