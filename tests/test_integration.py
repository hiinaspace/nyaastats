"""Integration tests using the example RSS fixture."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from whenever import Instant

from nyaastats.models import StatsData, TorrentData
from nyaastats.rss_fetcher import RSSFetcher
from nyaastats.scheduler import Scheduler
from nyaastats.tracker import TrackerScraper


@pytest.fixture
def example_rss_content():
    """Load the example RSS fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "example.rss"
    return fixture_path.read_text()


def test_end_to_end_rss_processing(temp_db, example_rss_content):
    """Test complete RSS processing pipeline."""
    # Setup RSS fetcher
    import httpx

    rss_fetcher = RSSFetcher(temp_db, httpx.Client())

    # Mock HTTP response
    mock_response = Mock()
    mock_response.text = example_rss_content
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        # Use real guessit to test Language object conversion
        # Process the feed
        processed = rss_fetcher.process_feed()

        # Verify processing (example.rss has 75 items)
        assert processed == 75

        # Check that torrents were inserted
        assert temp_db.get_torrent_exists("f87db04e1531c5f6fbaca3e6e2876f9c2982f46a")
        assert temp_db.get_torrent_exists("20a760df29d3bea030cf5f920ae5c932ca78f1b3")

        # Check torrent details
        with temp_db.get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM torrents WHERE infohash = ?",
                ("f87db04e1531c5f6fbaca3e6e2876f9c2982f46a",),
            )
            row = cursor.fetchone()

            assert row is not None
            assert row["filename"] == "[LonelyChaser-Inka] Tongari Boushi no Memoru 12"
            assert row["nyaa_id"] == 1993842
            assert row["size_bytes"] == int(1.1 * 1024**3)
            assert not row["trusted"]
            assert not row["remake"]
            # Check that guessit data was processed and stored as JSON
            assert row["guessit_data"] is not None
            # With real guessit, we verify the data was processed without errors
            # but don't assume specific guessit results

            # Check initial stats were inserted
            cursor = conn.execute(
                "SELECT * FROM stats WHERE infohash = ?",
                ("f87db04e1531c5f6fbaca3e6e2876f9c2982f46a",),
            )
            stats_row = cursor.fetchone()

            assert stats_row is not None
            assert stats_row["seeders"] == 14
            assert stats_row["leechers"] == 5
            assert stats_row["downloads"] == 26


def test_scheduler_integration(temp_db):
    """Test scheduler integration with real RSS data."""
    # Create minimal RSS content for testing
    test_rss_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
    <channel>
        <title>Nyaa - Test Feed</title>
        <item>
            <title>[LonelyChaser-Inka] Tongari Boushi no Memoru 12</title>
            <link>https://nyaa.si/download/1993842.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/1993842</guid>
            <pubDate>Wed, 16 Jul 2025 01:53:15 -0000</pubDate>
            <nyaa:seeders>14</nyaa:seeders>
            <nyaa:leechers>5</nyaa:leechers>
            <nyaa:downloads>26</nyaa:downloads>
            <nyaa:infoHash>f87db04e1531c5f6fbaca3e6e2876f9c2982f46a</nyaa:infoHash>
            <nyaa:size>1.1 GiB</nyaa:size>
            <nyaa:trusted>No</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
        <item>
            <title>[ToonsHub] The Shiunji Family Children S01E12 1080p CR WEB-DL AAC2.0 H.264 (Shiunji-ke no Kodomotachi, Dual-Audio, Multi-Subs)</title>
            <link>https://nyaa.si/download/1993841.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/1993841</guid>
            <pubDate>Wed, 16 Jul 2025 01:34:58 -0000</pubDate>
            <nyaa:seeders>21</nyaa:seeders>
            <nyaa:leechers>6</nyaa:leechers>
            <nyaa:downloads>37</nyaa:downloads>
            <nyaa:infoHash>20a760df29d3bea030cf5f920ae5c932ca78f1b3</nyaa:infoHash>
            <nyaa:size>1.4 GiB</nyaa:size>
            <nyaa:trusted>No</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
    </channel>
</rss>"""

    # Setup components
    import httpx

    rss_fetcher = RSSFetcher(temp_db, httpx.Client())
    scheduler = Scheduler(temp_db)

    # Mock HTTP response and process RSS
    mock_response = Mock()
    mock_response.text = test_rss_content
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        with patch("nyaastats.rss_fetcher.guessit.guessit") as mock_guessit:
            mock_guessit.return_value = {"title": "Test Anime", "type": "episode"}

            # Process RSS
            processed = rss_fetcher.process_feed()
            assert processed == 2

            # Check metrics
            metrics = scheduler.get_metrics()
            assert metrics["torrents_total"] == 2
            assert metrics["torrents_active"] == 2
            assert metrics["stats_total"] == 2  # Initial RSS stats

            # Check schedule summary
            summary = scheduler.get_schedule_summary()
            assert "hourly" in summary  # New torrents should be in hourly schedule
            assert summary["hourly"] == 2

            # Get due torrents (should be all of them since they're new)
            due_torrents = scheduler.get_due_torrents()
            assert len(due_torrents) == 2
            assert "f87db04e1531c5f6fbaca3e6e2876f9c2982f46a" in due_torrents
            assert "20a760df29d3bea030cf5f920ae5c932ca78f1b3" in due_torrents


def test_tracker_integration(temp_db):
    """Test tracker integration with processed RSS data."""
    # Create minimal RSS content for testing
    test_rss_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
    <channel>
        <title>Nyaa - Test Feed</title>
        <item>
            <title>[LonelyChaser-Inka] Tongari Boushi no Memoru 12</title>
            <link>https://nyaa.si/download/1993842.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/1993842</guid>
            <pubDate>Wed, 16 Jul 2025 01:53:15 -0000</pubDate>
            <nyaa:seeders>14</nyaa:seeders>
            <nyaa:leechers>5</nyaa:leechers>
            <nyaa:downloads>26</nyaa:downloads>
            <nyaa:infoHash>f87db04e1531c5f6fbaca3e6e2876f9c2982f46a</nyaa:infoHash>
            <nyaa:size>1.1 GiB</nyaa:size>
            <nyaa:trusted>No</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
        <item>
            <title>[ToonsHub] The Shiunji Family Children S01E12 1080p CR WEB-DL AAC2.0 H.264 (Shiunji-ke no Kodomotachi, Dual-Audio, Multi-Subs)</title>
            <link>https://nyaa.si/download/1993841.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/1993841</guid>
            <pubDate>Wed, 16 Jul 2025 01:34:58 -0000</pubDate>
            <nyaa:seeders>21</nyaa:seeders>
            <nyaa:leechers>6</nyaa:leechers>
            <nyaa:downloads>37</nyaa:downloads>
            <nyaa:infoHash>20a760df29d3bea030cf5f920ae5c932ca78f1b3</nyaa:infoHash>
            <nyaa:size>1.4 GiB</nyaa:size>
            <nyaa:trusted>No</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
    </channel>
</rss>"""

    # Setup components
    import httpx

    rss_fetcher = RSSFetcher(temp_db, httpx.Client())
    tracker_scraper = TrackerScraper(temp_db, httpx.Client())
    scheduler = Scheduler(temp_db)

    # Process RSS first
    mock_response = Mock()
    mock_response.text = test_rss_content
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        with patch("nyaastats.rss_fetcher.guessit.guessit") as mock_guessit:
            mock_guessit.return_value = {"title": "Test Anime", "type": "episode"}

            processed = rss_fetcher.process_feed()
            assert processed == 2

    # Get due torrents
    due_torrents = scheduler.get_due_torrents()
    assert len(due_torrents) == 2

    # Mock tracker scraping
    mock_tracker_results = {
        "f87db04e1531c5f6fbaca3e6e2876f9c2982f46a": StatsData(
            seeders=20,
            leechers=3,
            downloads=30,
        ),
        "20a760df29d3bea030cf5f920ae5c932ca78f1b3": StatsData(
            seeders=25,
            leechers=4,
            downloads=40,
        ),
    }

    with patch.object(tracker_scraper, "scrape_batch") as mock_scrape:
        mock_scrape.return_value = mock_tracker_results

        # Scrape the due torrents
        results = tracker_scraper.scrape_batch(due_torrents)

        # Update stats
        tracker_scraper.update_batch_stats(results)

        # Verify stats were updated
        stats1 = temp_db.get_recent_stats(
            "f87db04e1531c5f6fbaca3e6e2876f9c2982f46a", limit=1
        )
        stats2 = temp_db.get_recent_stats(
            "20a760df29d3bea030cf5f920ae5c932ca78f1b3", limit=1
        )

        assert len(stats1) == 1
        assert len(stats2) == 1

        # Check the most recent stats (should be from our scrape)
        assert stats1[0]["seeders"] == 20
        assert stats1[0]["leechers"] == 3
        assert stats1[0]["downloads"] == 30

        assert stats2[0]["seeders"] == 25
        assert stats2[0]["leechers"] == 4
        assert stats2[0]["downloads"] == 40


def test_dead_torrent_detection(temp_db):
    """Test dead torrent detection workflow."""

    # Insert a torrent manually
    torrent_data = TorrentData(
        infohash="deadbeef1234567890deadbeef1234567890dead",
        filename="dead.torrent",
        pubdate=Instant.from_utc(2025, 1, 1, 12, 0, 0),
        size_bytes=1000000,
        nyaa_id=99999,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
    )
    temp_db.insert_torrent(torrent_data)

    # Setup tracker scraper
    import httpx

    tracker_scraper = TrackerScraper(temp_db, httpx.Client())

    # Simulate 3 consecutive zero responses
    zero_stats = StatsData(seeders=0, leechers=0, downloads=0)

    for i in range(3):
        tracker_scraper.update_stats(
            torrent_data.infohash,
            zero_stats,
            timestamp=torrent_data.pubdate.add(hours=i),
        )

    # Check that torrent watests/test_integration.py::test_dead_torrent_detections marked as dead
    with temp_db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT status FROM torrents WHERE infohash = ?",
            (torrent_data.infohash,),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["status"] == "dead"

    # Check that dead torrent is not in due list
    scheduler = Scheduler(temp_db)
    due_torrents = scheduler.get_due_torrents()
    assert torrent_data.infohash not in due_torrents


def test_guessit_failure_handling(temp_db):
    """Test handling of guessit failures."""
    # Create RSS content with a problematic filename
    rss_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
    <channel>
        <title>Nyaa - Test Feed</title>
        <item>
            <title>ThisFilenameWillCauseGuessitToFail</title>
            <link>https://nyaa.si/download/999999.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/999999</guid>
            <pubDate>Wed, 16 Jul 2025 01:53:15 -0000</pubDate>
            <nyaa:seeders>1</nyaa:seeders>
            <nyaa:leechers>0</nyaa:leechers>
            <nyaa:downloads>1</nyaa:downloads>
            <nyaa:infoHash>failedbeef1234567890failedbeef1234567890</nyaa:infoHash>
            <nyaa:size>100 MiB</nyaa:size>
            <nyaa:trusted>No</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
    </channel>
</rss>"""

    import httpx

    rss_fetcher = RSSFetcher(temp_db, httpx.Client())

    mock_response = Mock()
    mock_response.text = rss_content
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        # Mock guessit to raise an exception
        with patch("nyaastats.rss_fetcher.guessit.guessit") as mock_guessit:
            mock_guessit.side_effect = Exception("Guessit parsing failed")

            # Process should still work despite guessit failure
            processed = rss_fetcher.process_feed()
            assert processed == 1

            # Check that torrent was inserted despite guessit failure
            assert temp_db.get_torrent_exists(
                "failedbeef1234567890failedbeef1234567890"
            )

            # Check that guessit data is None when parsing fails
            with temp_db.get_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM torrents WHERE infohash = ?",
                    ("failedbeef1234567890failedbeef1234567890",),
                )
                row = cursor.fetchone()

                assert row is not None
                assert row["filename"] == "ThisFilenameWillCauseGuessitToFail"
                assert row["guessit_data"] is None
