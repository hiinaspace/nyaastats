from unittest.mock import Mock, patch

from whenever import Instant

from nyaastats.models import StatsData, TorrentData


def test_scrape_batch_success(tracker_scraper):
    """Test successful batch scraping."""
    infohashes = [
        "abcdef1234567890abcdef1234567890abcdef12",
        "fedcba0987654321fedcba0987654321fedcba09",
    ]

    # Mock bencode response
    mock_response_data = {
        b"files": {
            bytes.fromhex("abcdef1234567890abcdef1234567890abcdef12"): {
                b"complete": 10,
                b"incomplete": 2,
                b"downloaded": 100,
            },
            bytes.fromhex("fedcba0987654321fedcba0987654321fedcba09"): {
                b"complete": 5,
                b"incomplete": 1,
                b"downloaded": 50,
            },
        }
    }

    with patch("nyaastats.tracker.bencodepy.decode") as mock_decode:
        mock_decode.return_value = mock_response_data

        with patch("nyaastats.tracker.httpx.Client") as mock_client:
            mock_response = Mock()
            mock_response.content = b"dummy"
            mock_response.raise_for_status = Mock()
            mock_client.return_value.get.return_value = mock_response

            results = tracker_scraper.scrape_batch(infohashes)

            assert len(results) == 2
            expected_stats1 = StatsData(seeders=10, leechers=2, downloads=100)
            assert (
                results["abcdef1234567890abcdef1234567890abcdef12"] == expected_stats1
            )
            expected_stats2 = StatsData(seeders=5, leechers=1, downloads=50)
            assert (
                results["fedcba0987654321fedcba0987654321fedcba09"] == expected_stats2
            )


def test_scrape_batch_empty_list(tracker_scraper):
    """Test scraping with empty infohash list."""
    results = tracker_scraper.scrape_batch([])
    assert results == {}


def test_scrape_batch_invalid_infohash(tracker_scraper):
    """Test scraping with invalid infohash."""
    infohashes = ["invalid_hex", "abcdef1234567890abcdef1234567890abcdef12"]

    # Mock bencode response for valid infohash only
    mock_response_data = {
        b"files": {
            bytes.fromhex("abcdef1234567890abcdef1234567890abcdef12"): {
                b"complete": 10,
                b"incomplete": 2,
                b"downloaded": 100,
            }
        }
    }

    with patch("nyaastats.tracker.bencodepy.decode") as mock_decode:
        mock_decode.return_value = mock_response_data

        with patch("nyaastats.tracker.httpx.Client") as mock_client:
            mock_response = Mock()
            mock_response.content = b"dummy"
            mock_response.raise_for_status = Mock()
            mock_client.return_value.get.return_value = mock_response

            results = tracker_scraper.scrape_batch(infohashes)

            # Should only return result for valid infohash
            assert len(results) == 1
            assert "abcdef1234567890abcdef1234567890abcdef12" in results


def test_scrape_batch_missing_torrents(tracker_scraper):
    """Test scraping when some torrents are missing from tracker response."""
    infohashes = [
        "abcdef1234567890abcdef1234567890abcdef12",
        "fedcba0987654321fedcba0987654321fedcba09",
    ]

    # Mock bencode response with only one torrent
    mock_response_data = {
        b"files": {
            bytes.fromhex("abcdef1234567890abcdef1234567890abcdef12"): {
                b"complete": 10,
                b"incomplete": 2,
                b"downloaded": 100,
            }
        }
    }

    with patch("nyaastats.tracker.bencodepy.decode") as mock_decode:
        mock_decode.return_value = mock_response_data

        with patch("nyaastats.tracker.httpx.Client") as mock_client:
            mock_response = Mock()
            mock_response.content = b"dummy"
            mock_response.raise_for_status = Mock()
            mock_client.return_value.get.return_value = mock_response

            results = tracker_scraper.scrape_batch(infohashes)

            assert len(results) == 2
            expected_stats = StatsData(seeders=10, leechers=2, downloads=100)
            assert results["abcdef1234567890abcdef1234567890abcdef12"] == expected_stats
            # Missing torrent should get zeros
            expected_zero_stats = StatsData(seeders=0, leechers=0, downloads=0)
            assert (
                results["fedcba0987654321fedcba0987654321fedcba09"]
                == expected_zero_stats
            )


def test_scrape_batch_http_error(tracker_scraper):
    """Test scraping with HTTP error."""
    infohashes = ["abcdef1234567890abcdef1234567890abcdef12"]

    with patch.object(tracker_scraper.client, "get") as mock_get:
        mock_get.side_effect = Exception("HTTP Error")

        results = tracker_scraper.scrape_batch(infohashes)

        # Should return empty dict for HTTP errors (don't count as individual torrent failures)
        assert results == {}


def test_update_stats(tracker_scraper):
    """Test updating stats for a single torrent."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"
    stats = StatsData(seeders=10, leechers=2, downloads=100)

    # Since we use controlled time through fixtures, no mocking needed
    tracker_scraper.update_stats(infohash, stats)

    # Check that stats were inserted
    recent_stats = tracker_scraper.db.get_recent_stats(infohash, limit=1)
    assert len(recent_stats) == 1
    assert recent_stats[0]["seeders"] == 10
    assert recent_stats[0]["leechers"] == 2
    assert recent_stats[0]["downloads"] == 100


def test_should_mark_dead_true(tracker_scraper):
    """Test marking torrent as dead when it has 3 consecutive zero responses."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # Insert 3 consecutive zero stats
    zero_stats = StatsData(seeders=0, leechers=0, downloads=0)
    for i in range(3):
        timestamp = Instant.from_utc(2025, 1, 1, 12, i, 0)
        tracker_scraper.db.insert_stats(infohash, zero_stats, timestamp)

    assert tracker_scraper._should_mark_dead(infohash)


def test_should_mark_dead_false_not_enough_stats(tracker_scraper):
    """Test not marking torrent as dead when there are less than 3 stats."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # Insert only 2 stats
    zero_stats = StatsData(seeders=0, leechers=0, downloads=0)
    for i in range(2):
        timestamp = Instant.from_utc(2025, 1, 1, 12, i, 0)
        tracker_scraper.db.insert_stats(infohash, zero_stats, timestamp)

    assert not tracker_scraper._should_mark_dead(infohash)


def test_should_mark_dead_false_non_zero_stats(tracker_scraper):
    """Test not marking torrent as dead when it has non-zero stats."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # Insert mixed stats
    stats_data = [
        StatsData(seeders=0, leechers=0, downloads=0),
        StatsData(seeders=1, leechers=0, downloads=5),  # Non-zero
        StatsData(seeders=0, leechers=0, downloads=0),
    ]

    for i, stats in enumerate(stats_data):
        timestamp = Instant.from_utc(2025, 1, 1, 12, i, 0)
        tracker_scraper.db.insert_stats(infohash, stats, timestamp)

    assert not tracker_scraper._should_mark_dead(infohash)


def test_update_stats_marks_dead(tracker_scraper):
    """Test that update_stats marks torrent as dead when appropriate."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # First insert a torrent
    torrent_data = TorrentData(
        infohash=infohash,
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 12, 0, 0),
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    tracker_scraper.db.insert_torrent(torrent_data)

    # Remove the initial RSS stats and insert 2 previous zero stats
    zero_stats = StatsData(seeders=0, leechers=0, downloads=0)
    with tracker_scraper.db.get_conn() as conn:
        conn.execute("DELETE FROM stats WHERE infohash = ?", (infohash,))
        conn.commit()

    for i in range(2):
        timestamp = Instant.from_utc(
            2025, 1, 1, 11, i, 0
        )  # Use different hour to avoid conflict
        tracker_scraper.db.insert_stats(infohash, zero_stats, timestamp)

    # Update with another zero stat (should mark as dead)
    # Since we use controlled time through fixtures, no mocking needed
    tracker_scraper.update_stats(infohash, zero_stats)

    # Check that torrent was marked as dead
    with tracker_scraper.db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT status FROM torrents WHERE infohash = ?", (infohash,)
        )
        row = cursor.fetchone()
        assert row["status"] == "dead"


def test_update_batch_stats(tracker_scraper):
    """Test updating stats for multiple torrents."""
    results = {
        "abcdef1234567890abcdef1234567890abcdef12": StatsData(
            seeders=10,
            leechers=2,
            downloads=100,
        ),
        "fedcba0987654321fedcba0987654321fedcba09": StatsData(
            seeders=5,
            leechers=1,
            downloads=50,
        ),
    }

    with patch.object(tracker_scraper, "update_stats") as mock_update:
        tracker_scraper.update_batch_stats(results)

        # Check that update_stats was called for each torrent
        assert mock_update.call_count == 2
        mock_update.assert_any_call(
            "abcdef1234567890abcdef1234567890abcdef12",
            StatsData(seeders=10, leechers=2, downloads=100),
        )
        mock_update.assert_any_call(
            "fedcba0987654321fedcba0987654321fedcba09",
            StatsData(seeders=5, leechers=1, downloads=50),
        )


def test_scrape_batch_url_encoding(tracker_scraper):
    """Test that infohashes are properly URL encoded."""
    infohashes = ["abcdef1234567890abcdef1234567890abcdef12"]

    mock_response = Mock()
    mock_response.content = b"dummy"
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(
        tracker_scraper.client, "get", return_value=mock_response
    ) as mock_get:
        with patch("nyaastats.tracker.bencodepy.decode") as mock_decode:
            mock_decode.return_value = {b"files": {}}

            tracker_scraper.scrape_batch(infohashes)

            # Check that the URL was properly constructed
            called_url = mock_get.call_args[0][0]
            assert "info_hash=" in called_url
            assert tracker_scraper.tracker_url in called_url


def test_scrape_batch_bencode_decode_error(tracker_scraper):
    """Test scraping when bencode decoding fails."""
    infohashes = ["abcdef1234567890abcdef1234567890abcdef12"]

    mock_response = Mock()
    mock_response.content = b"invalid_bencode"
    mock_response.raise_for_status = Mock()

    with patch.object(tracker_scraper.client, "get", return_value=mock_response):
        with patch("nyaastats.tracker.bencodepy.decode") as mock_decode:
            mock_decode.side_effect = Exception("Bencode decode error")

            results = tracker_scraper.scrape_batch(infohashes)

            # Should return empty dict for decode errors (don't count as individual torrent failures)
            assert results == {}


def test_update_batch_stats_empty_results(tracker_scraper):
    """Test update_batch_stats with empty results (simulates HTTP error)."""
    # Should handle empty results gracefully without updating any stats
    tracker_scraper.update_batch_stats({})

    # No exception should be raised, and no stats should be updated
    # This is mainly to ensure the method doesn't crash on empty input


def test_update_batch_stats_with_data(tracker_scraper):
    """Test update_batch_stats with actual data."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"
    stats = StatsData(seeders=10, leechers=2, downloads=100)

    # Insert a torrent first so we can update its stats
    torrent_data = TorrentData(
        infohash=infohash,
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 12, 0, 0),
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    tracker_scraper.db.insert_torrent(torrent_data)

    # Update batch stats
    tracker_scraper.update_batch_stats({infohash: stats})

    # Verify stats were updated
    recent_stats = tracker_scraper.db.get_recent_stats(infohash, limit=1)
    assert len(recent_stats) == 1
    assert recent_stats[0]["seeders"] == 10
    assert recent_stats[0]["leechers"] == 2
    assert recent_stats[0]["downloads"] == 100


def test_http_error_does_not_count_toward_dead_detection(tracker_scraper):
    """Test that HTTP errors don't count toward dead torrent detection."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # First insert a torrent
    torrent_data = TorrentData(
        infohash=infohash,
        filename="test.mkv",
        pubdate=Instant.from_utc(2025, 1, 1, 12, 0, 0),
        size_bytes=1000000,
        nyaa_id=12345,
        trusted=False,
        remake=False,
        seeders=5,
        leechers=1,
        downloads=50,
        guessit_data=None,
    )
    tracker_scraper.db.insert_torrent(torrent_data)

    # Simulate HTTP error - should return empty dict
    with patch.object(tracker_scraper.client, "get") as mock_get:
        mock_get.side_effect = Exception("HTTP Error")

        results = tracker_scraper.scrape_batch([infohash])
        tracker_scraper.update_batch_stats(results)

    # No new stats should be inserted due to HTTP error
    recent_stats = tracker_scraper.db.get_recent_stats(infohash, limit=10)
    # Should only have the initial RSS stats, no new zero stats from HTTP error
    assert len(recent_stats) == 1
    assert recent_stats[0]["seeders"] == 5  # Original RSS data

    # Torrent should still be active (not marked as dead)
    with tracker_scraper.db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT status FROM torrents WHERE infohash = ?", (infohash,)
        )
        row = cursor.fetchone()
        assert row["status"] == "active"
