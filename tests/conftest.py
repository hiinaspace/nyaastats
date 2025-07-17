import httpx
import pytest
from whenever import Instant

from nyaastats.database import Database
from nyaastats.rss_fetcher import RSSFetcher
from nyaastats.scheduler import Scheduler
from nyaastats.tracker import TrackerScraper


@pytest.fixture
def fixed_time():
    """Provide a fixed time for testing."""
    return Instant.from_utc(2025, 1, 1, 12, 0, 0)


@pytest.fixture
def temp_db(fixed_time):
    """Create a temporary database for testing."""
    db = Database(":memory:", now_func=lambda: fixed_time)
    yield db


@pytest.fixture
def mock_client():
    """Create a mock HTTP client for testing."""
    return httpx.Client(timeout=30.0)


@pytest.fixture
def rss_fetcher(temp_db, mock_client, fixed_time):
    """Create RSS fetcher instance."""
    return RSSFetcher(temp_db, mock_client, now_func=lambda: fixed_time)


@pytest.fixture
def tracker_scraper(temp_db, mock_client, fixed_time):
    """Create tracker scraper instance."""
    return TrackerScraper(temp_db, mock_client, now_func=lambda: fixed_time)


@pytest.fixture
def scheduler(temp_db):
    """Create scheduler instance."""
    return Scheduler(temp_db, batch_size=10)
