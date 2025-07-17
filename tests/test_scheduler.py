from whenever import Instant

from nyaastats.models import StatsData, TorrentData


def test_get_due_torrents_never_scraped(scheduler):
    """Test getting torrents that have never been scraped."""
    # Insert a torrent that has never been scraped
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Remove the initial RSS stats to simulate never scraped
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash in due_torrents


def test_get_due_torrents_recent_hourly(scheduler):
    """Test getting torrents in hourly schedule (first 48 hours)."""
    # Insert a torrent published 1 hour ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Delete the initial RSS stat and insert stats from 2 hours ago
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    # Insert stats from 2 hours ago (should be due for hourly scraping)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2025, 1, 1, 10, 0, 0),  # 2 hours ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash in due_torrents


def test_get_due_torrents_recent_not_due(scheduler):
    """Test torrents that are not due for scraping."""
    # Insert a torrent published 1 hour ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Insert stats from 30 minutes ago (should not be due for hourly scraping)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2025, 1, 1, 11, 30, 0),  # 30 minutes ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash not in due_torrents


def test_get_due_torrents_four_hour_schedule(scheduler):
    """Test torrents in 4-hour schedule (days 3-7)."""
    # Insert a torrent published 5 days ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2024, 12, 27, 12, 0, 0),  # 5 days ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Delete the initial RSS stat and insert stats from 5 hours ago
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    # Insert stats from 5 hours ago (should be due for 4-hour scraping)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2025, 1, 1, 7, 0, 0),  # 5 hours ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash in due_torrents


def test_get_due_torrents_daily_schedule(scheduler):
    """Test torrents in daily schedule (weeks 2-4)."""
    # Insert a torrent published 20 days ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2024, 12, 12, 12, 0, 0),  # 20 days ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Delete the initial RSS stat and insert stats from 2 days ago
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    # Insert stats from 2 days ago (should be due for daily scraping)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2024, 12, 30, 12, 0, 0),  # 2 days ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash in due_torrents


def test_get_due_torrents_weekly_schedule(scheduler):
    """Test torrents in weekly schedule (months 2-6)."""
    # Insert a torrent published 120 days ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2024, 9, 3, 12, 0, 0),  # ~120 days ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Delete the initial RSS stat and insert stats from 8 days ago
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    # Insert stats from 8 days ago (should be due for weekly scraping)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2024, 12, 24, 12, 0, 0),  # 8 days ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash in due_torrents


def test_get_due_torrents_never_schedule(scheduler):
    """Test torrents that should never be scraped (>6 months)."""
    # Insert a torrent published 200 days ago
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2024, 6, 14, 12, 0, 0),  # ~200 days ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Insert stats from 10 days ago (should not be due - too old)
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2024, 12, 22, 12, 0, 0),  # 10 days ago
    )

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash not in due_torrents


def test_get_due_torrents_inactive_status(scheduler):
    """Test that inactive torrents are not included."""
    # Insert a torrent and mark it as dead
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)
    scheduler.db.mark_torrent_status(torrent_data.infohash, "dead")

    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash not in due_torrents


def test_get_due_torrents_batch_size(scheduler):
    """Test that batch size is respected."""
    # Insert more torrents than batch size
    infohashes = []
    for i in range(15):  # More than batch_size of 10
        infohash = f"abcdef1234567890abcdef1234567890abcdef{i:02d}"
        infohashes.append(infohash)

        torrent_data = TorrentData(
            infohash=infohash,
            filename=f"test{i}.mkv",
            pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
            size_bytes=1000000,
            nyaa_id=12345 + i,
            trusted=False,
            remake=False,
            seeders=5,
            leechers=1,
            downloads=50,
        )
        scheduler.db.insert_torrent(torrent_data)

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
    # Insert various types of torrents
    torrents = [
        ("abcdef1234567890abcdef1234567890abcdef12", "active"),
        ("fedcba0987654321fedcba0987654321fedcba09", "dead"),
        ("123456789abcdef0123456789abcdef012345678", "guessit_failed"),
        ("876543210fedcba9876543210fedcba987654321", "active"),
    ]

    for infohash, status in torrents:
        torrent_data = TorrentData(
            infohash=infohash,
            filename="test.mkv",
            pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
            size_bytes=1000000,
            nyaa_id=12345,
            trusted=False,
            remake=False,
            seeders=5,
            leechers=1,
            downloads=50,
        )
        scheduler.db.insert_torrent(torrent_data)

        if status != "active":
            scheduler.db.mark_torrent_status(infohash, status)

    # Insert some stats
    scheduler.db.insert_stats(
        "abcdef1234567890abcdef1234567890abcdef12",
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2025, 1, 1, 12, 0, 0),  # base_time
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
    # Use the same fixed time as the scheduler

    # Insert a torrent in hourly schedule (1 hour ago from fixed time)
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    scheduler.db.insert_torrent(torrent_data)

    # Remove any initial stats created by insert_torrent and insert our own
    with scheduler.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (torrent_data.infohash,))
        conn.commit()

    # Insert stats that are > 1 hour ago to make it due
    scheduler.db.insert_stats(
        torrent_data.infohash,
        StatsData(seeders=5, leechers=1, downloads=50),
        Instant.from_utc(2025, 1, 1, 10, 30, 0),  # 1.5 hours ago from fixed time
    )

    schedule_info = scheduler.get_torrent_scrape_schedule(torrent_data.infohash)

    assert schedule_info is not None
    assert schedule_info["infohash"] == torrent_data.infohash
    assert schedule_info["status"] == "active"
    assert schedule_info["schedule_type"] == "hourly"
    assert schedule_info["is_due"] == 1  # Should be due


def test_get_torrent_scrape_schedule_nonexistent(scheduler):
    """Test getting scrape schedule for non-existent torrent."""
    schedule_info = scheduler.get_torrent_scrape_schedule("nonexistent")
    assert schedule_info is None


def test_get_schedule_summary(scheduler):
    """Test getting schedule summary."""
    # Insert torrents in different schedules with specific dates
    torrents = [
        (
            "abcdef1234567890abcdef1234567890abcdef12",
            Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago - hourly
        ),
        (
            "fedcba0987654321fedcba0987654321fedcba09",
            Instant.from_utc(2024, 12, 27, 12, 0, 0),  # 5 days ago - every_4_hours
        ),
        (
            "123456789abcdef0123456789abcdef012345678",
            Instant.from_utc(2024, 12, 12, 12, 0, 0),  # 20 days ago - daily
        ),
        (
            "876543210fedcba9876543210fedcba987654321",
            Instant.from_utc(2024, 9, 3, 12, 0, 0),  # ~120 days ago - weekly
        ),
        (
            "abcdef9876543210abcdef9876543210abcdef98",
            Instant.from_utc(2024, 6, 14, 12, 0, 0),  # ~200 days ago - never
        ),
    ]

    for infohash, pubdate in torrents:
        torrent_data = TorrentData(
            infohash=infohash,
            filename="test.mkv",
            pubdate=pubdate,
            size_bytes=1000000,
            nyaa_id=12345,
            trusted=False,
            remake=False,
            seeders=5,
            leechers=1,
            downloads=50,
        )
        scheduler.db.insert_torrent(torrent_data)

        # Insert a scrape stat so they're not in 'never_scraped'
        scheduler.db.insert_stats(
            infohash,
            StatsData(seeders=5, leechers=1, downloads=50),
            Instant.from_utc(2025, 1, 1, 11, 0, 0),  # 1 hour ago
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
