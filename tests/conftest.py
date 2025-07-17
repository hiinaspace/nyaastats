import pytest
import httpx

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
def mock_client():
    """Create a mock HTTP client for testing."""
    return httpx.Client(timeout=30.0)


@pytest.fixture
def rss_fetcher(temp_db, mock_client):
    """Create RSS fetcher instance."""
    return RSSFetcher(temp_db, mock_client)


@pytest.fixture
def tracker_scraper(temp_db, mock_client):
    """Create tracker scraper instance."""
    return TrackerScraper(temp_db, mock_client)


@pytest.fixture
def scheduler(temp_db):
    """Create scheduler instance."""
    return Scheduler(temp_db, batch_size=10)
