from datetime import datetime, timedelta

import pytest

from nyaastats.database import Database
from nyaastats.scheduler import Scheduler


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db = Database(":memory:")
    yield db


@pytest.fixture
def scheduler(temp_db):
    """Create scheduler instance."""
    return Scheduler(temp_db, batch_size=10)


def test_get_due_torrents_never_scraped(scheduler):
    """Test getting torrents that have never been scraped."""
    # Insert a torrent that has never been scraped
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": datetime.utcnow() - timedelta(hours=1),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Remove the initial RSS stats to simulate never scraped
    with scheduler.db.get_conn() as conn:
        conn.execute(
            "DELETE FROM stats WHERE infohash = ?", (torrent_data["infohash"],)
        )
        conn.commit()

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] in due_torrents


def test_get_due_torrents_recent_hourly(scheduler):
    """Test getting torrents in hourly schedule (first 48 hours)."""
    base_time = datetime.utcnow()

    # Insert a torrent published 1 hour ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(hours=1),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 2 hours ago (should be due for hourly scraping)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(hours=2),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] in due_torrents


def test_get_due_torrents_recent_not_due(scheduler):
    """Test torrents that are not due for scraping."""
    base_time = datetime.utcnow()

    # Insert a torrent published 1 hour ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(hours=1),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 30 minutes ago (should not be due for hourly scraping)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(minutes=30),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] not in due_torrents


def test_get_due_torrents_four_hour_schedule(scheduler):
    """Test torrents in 4-hour schedule (days 3-7)."""
    base_time = datetime.utcnow()

    # Insert a torrent published 5 days ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(days=5),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 5 hours ago (should be due for 4-hour scraping)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(hours=5),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] in due_torrents


def test_get_due_torrents_daily_schedule(scheduler):
    """Test torrents in daily schedule (weeks 2-4)."""
    base_time = datetime.utcnow()

    # Insert a torrent published 20 days ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(days=20),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 2 days ago (should be due for daily scraping)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(days=2),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] in due_torrents


def test_get_due_torrents_weekly_schedule(scheduler):
    """Test torrents in weekly schedule (months 2-6)."""
    base_time = datetime.utcnow()

    # Insert a torrent published 120 days ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(days=120),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 8 days ago (should be due for weekly scraping)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(days=8),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] in due_torrents


def test_get_due_torrents_never_schedule(scheduler):
    """Test torrents that should never be scraped (>6 months)."""
    base_time = datetime.utcnow()

    # Insert a torrent published 200 days ago
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(days=200),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 10 days ago (should not be due - too old)
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(days=10),
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] not in due_torrents


def test_get_due_torrents_inactive_status(scheduler):
    """Test that inactive torrents are not included."""
    base_time = datetime.utcnow()

    # Insert a torrent and mark it as dead
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(hours=1),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})
    scheduler.db.mark_torrent_status(torrent_data["infohash"], "dead")

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data["infohash"] not in due_torrents


def test_get_due_torrents_batch_size(scheduler):
    """Test that batch size is respected."""
    base_time = datetime.utcnow()

    # Insert more torrents than batch size
    infohashes = []
    for i in range(15):  # More than batch_size of 10
        infohash = f"abcdef1234567890abcdef1234567890abcdef{i:02d}"
        infohashes.append(infohash)

        torrent_data = {
            "infohash": infohash,
            "filename": f"test{i}.mkv",
            "pubdate": base_time - timedelta(hours=1),
            "size_bytes": 1000000,
            "nyaa_id": 12345 + i,
            "trusted": False,
            "remake": False,
            "seeders": 5,
            "leechers": 1,
            "downloads": 50,
        }
        scheduler.db.insert_torrent(torrent_data, {})

        # Remove initial stats to make them all due
        with scheduler.db.get_conn() as conn:
            conn.execute("DELETE FROM stats WHERE infohash = ?", (infohash,))
            conn.commit()

    due_torrents = scheduler.get_due_torrents()

    # Should be limited to batch size
    assert len(due_torrents) == 10

    # Should all be from our inserted torrents
    for infohash in due_torrents:
        assert infohash in infohashes


def test_get_metrics(scheduler):
    """Test getting system metrics."""
    base_time = datetime.utcnow()

    # Insert various types of torrents
    torrents = [
        ("abcdef1234567890abcdef1234567890abcdef12", "active"),
        ("fedcba0987654321fedcba0987654321fedcba09", "dead"),
        ("123456789abcdef0123456789abcdef012345678", "guessit_failed"),
        ("876543210fedcba9876543210fedcba987654321", "active"),
    ]

    for infohash, status in torrents:
        torrent_data = {
            "infohash": infohash,
            "filename": "test.mkv",
            "pubdate": base_time - timedelta(hours=1),
            "size_bytes": 1000000,
            "nyaa_id": 12345,
            "trusted": False,
            "remake": False,
            "seeders": 5,
            "leechers": 1,
            "downloads": 50,
        }
        scheduler.db.insert_torrent(torrent_data, {})

        if status != "active":
            scheduler.db.mark_torrent_status(infohash, status)

    # Insert some stats
    scheduler.db.insert_stats(
        "abcdef1234567890abcdef1234567890abcdef12",
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time,
    )

    metrics = scheduler.get_metrics()

    assert metrics["torrents_total"] == 4
    assert metrics["torrents_active"] == 2
    assert metrics["torrents_dead"] == 1
    assert metrics["torrents_guessit_failed"] == 1
    assert metrics["stats_total"] >= 4  # Including initial RSS stats
    assert metrics["stats_recent"] >= 1
    assert "queue_depth" in metrics


def test_get_torrent_scrape_schedule(scheduler):
    """Test getting scrape schedule for a specific torrent."""
    base_time = datetime.utcnow()

    # Insert a torrent in hourly schedule
    torrent_data = {
        "infohash": "abcdef1234567890abcdef1234567890abcdef12",
        "filename": "test.mkv",
        "pubdate": base_time - timedelta(hours=1),
        "size_bytes": 1000000,
        "nyaa_id": 12345,
        "trusted": False,
        "remake": False,
        "seeders": 5,
        "leechers": 1,
        "downloads": 50,
    }
    scheduler.db.insert_torrent(torrent_data, {})

    # Insert stats from 2 hours ago
    scheduler.db.insert_stats(
        torrent_data["infohash"],
        {"seeders": 5, "leechers": 1, "downloads": 50},
        base_time - timedelta(hours=2),
    )

    schedule_info = scheduler.get_torrent_scrape_schedule(torrent_data["infohash"])

    assert schedule_info is not None
    assert schedule_info["infohash"] == torrent_data["infohash"]
    assert schedule_info["status"] == "active"
    assert schedule_info["schedule_type"] == "hourly"
    assert schedule_info["is_due"] == 1  # Should be due


def test_get_torrent_scrape_schedule_nonexistent(scheduler):
    """Test getting scrape schedule for non-existent torrent."""
    schedule_info = scheduler.get_torrent_scrape_schedule("nonexistent")
    assert schedule_info is None


def test_get_schedule_summary(scheduler):
    """Test getting schedule summary."""
    base_time = datetime.utcnow()

    # Insert torrents in different schedules
    torrents = [
        (
            "abcdef1234567890abcdef1234567890abcdef12",
            base_time - timedelta(hours=1),
        ),  # hourly
        (
            "fedcba0987654321fedcba0987654321fedcba09",
            base_time - timedelta(days=5),
        ),  # every_4_hours
        (
            "123456789abcdef0123456789abcdef012345678",
            base_time - timedelta(days=20),
        ),  # daily
        (
            "876543210fedcba9876543210fedcba987654321",
            base_time - timedelta(days=120),
        ),  # weekly
        (
            "abcdef9876543210abcdef9876543210abcdef98",
            base_time - timedelta(days=200),
        ),  # never
    ]

    for infohash, pubdate in torrents:
        torrent_data = {
            "infohash": infohash,
            "filename": "test.mkv",
            "pubdate": pubdate,
            "size_bytes": 1000000,
            "nyaa_id": 12345,
            "trusted": False,
            "remake": False,
            "seeders": 5,
            "leechers": 1,
            "downloads": 50,
        }
        scheduler.db.insert_torrent(torrent_data, {})

        # Insert a scrape stat so they're not in 'never_scraped'
        scheduler.db.insert_stats(
            infohash,
            {"seeders": 5, "leechers": 1, "downloads": 50},
            base_time - timedelta(hours=1),
        )

    # Mark one as dead
    scheduler.db.mark_torrent_status("876543210fedcba9876543210fedcba987654321", "dead")

    summary = scheduler.get_schedule_summary()

    assert "hourly" in summary
    assert "every_4_hours" in summary
    assert "daily" in summary
    assert "dead" in summary
    assert "never" in summary

    # Check counts
    assert summary["hourly"] == 1
    assert summary["every_4_hours"] == 1
    assert summary["daily"] == 1
    assert summary["dead"] == 1
    assert summary["never"] == 1
