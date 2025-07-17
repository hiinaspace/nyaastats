import json

from whenever import Instant

from nyaastats.models import StatsData, TorrentData


def test_database_init(temp_db):
    """Test database initialization."""
    # Check that tables exist
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "torrents" in tables
        assert "stats" in tables


def test_database_schema(temp_db):
    """Test database schema is correct."""
    with temp_db.get_conn() as conn:
        # Check torrents table structure
        cursor = conn.execute("PRAGMA table_info(torrents)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "infohash": "TEXT",
            "filename": "TEXT",
            "pubdate": "TEXT",
            "size_bytes": "INTEGER",
            "nyaa_id": "INTEGER",
            "trusted": "BOOLEAN",
            "remake": "BOOLEAN",
            "status": "TEXT",
            "created_at": "TEXT",
            "guessit_data": "TEXT",
        }

        for col, col_type in expected_columns.items():
            assert col in columns
            assert columns[col] == col_type


def test_insert_torrent(temp_db):
    """Test inserting a torrent."""
    guessit_data = {
        "title": "Anime",
        "episode": 1,
        "screen_size": "1080p",
        "container": "mkv",
        "release_group": "Test",
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "source": "BluRay",
        "language": "en",
        "subtitles": ["en", "jp"],
        "custom_field": "custom_value",
    }

    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="[Test] Anime Episode 01 [1080p].mkv",
        pubdate=Instant.from_utc(2023, 1, 1, 12, 0, 0),
        size_bytes=1000000000,
        nyaa_id=12345,
        trusted=True,
        remake=False,
        seeders=10,
        leechers=2,
        downloads=100,
        guessit_data=guessit_data,
    )

    temp_db.insert_torrent(torrent_data)

    # Verify torrent was inserted
    with temp_db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT * FROM torrents WHERE infohash = ?", (torrent_data.infohash,)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["infohash"] == torrent_data.infohash
        assert row["filename"] == torrent_data.filename
        assert row["size_bytes"] == torrent_data.size_bytes
        assert row["nyaa_id"] == torrent_data.nyaa_id
        assert row["trusted"] == torrent_data.trusted
        assert row["remake"] == torrent_data.remake

        # Check that guessit data was stored as JSON
        stored_guessit = json.loads(row["guessit_data"])
        assert stored_guessit["title"] == "Anime"
        assert stored_guessit["episode"] == 1
        assert stored_guessit["custom_field"] == "custom_value"
        assert stored_guessit["screen_size"] == "1080p"
        assert stored_guessit["container"] == "mkv"
        assert stored_guessit["release_group"] == "Test"
        assert stored_guessit["subtitles"] == ["en", "jp"]

        # Verify initial stats were inserted
        cursor = conn.execute(
            "SELECT * FROM stats WHERE infohash = ?", (torrent_data.infohash,)
        )
        stats_row = cursor.fetchone()

        assert stats_row is not None
        assert stats_row["seeders"] == torrent_data.seeders
        assert stats_row["leechers"] == torrent_data.leechers
        assert stats_row["downloads"] == torrent_data.downloads


def test_insert_stats(temp_db):
    """Test inserting statistics."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"
    stats = StatsData(seeders=5, leechers=1, downloads=50)
    timestamp = Instant.from_utc(2023, 1, 2, 12, 0, 0)

    temp_db.insert_stats(infohash, stats, timestamp)

    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT * FROM stats WHERE infohash = ?", (infohash,))
        row = cursor.fetchone()

        assert row is not None
        assert row["infohash"] == infohash
        assert row["seeders"] == stats.seeders
        assert row["leechers"] == stats.leechers
        assert row["downloads"] == stats.downloads


def test_mark_torrent_status(temp_db):
    """Test marking torrent status."""
    # First insert a torrent
    torrent_data = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="[Test] Anime Episode 01 [1080p].mkv",
        pubdate=Instant.from_utc(2023, 1, 1, 12, 0, 0),
        size_bytes=1000000000,
        nyaa_id=12345,
        trusted=True,
        remake=False,
        seeders=10,
        leechers=2,
        downloads=100,
        guessit_data=None,
    )

    temp_db.insert_torrent(torrent_data)

    # Mark as dead
    temp_db.mark_torrent_status(torrent_data.infohash, "dead")

    with temp_db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT status FROM torrents WHERE infohash = ?",
            (torrent_data.infohash,),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["status"] == "dead"


def test_get_torrent_exists(temp_db):
    """Test checking if torrent exists."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # Should not exist initially
    assert not temp_db.get_torrent_exists(infohash)

    # Insert a torrent
    torrent_data = TorrentData(
        infohash=infohash,
        filename="[Test] Anime Episode 01 [1080p].mkv",
        pubdate=Instant.from_utc(2023, 1, 1, 12, 0, 0),
        size_bytes=1000000000,
        nyaa_id=12345,
        trusted=True,
        remake=False,
        seeders=10,
        leechers=2,
        downloads=100,
        guessit_data=None,
    )

    temp_db.insert_torrent(torrent_data)

    # Should exist now
    assert temp_db.get_torrent_exists(infohash)


def test_get_recent_stats(temp_db):
    """Test getting recent statistics."""
    infohash = "abcdef1234567890abcdef1234567890abcdef12"

    # Insert multiple stats
    stats_data = [
        (
            StatsData(seeders=10, leechers=2, downloads=100),
            Instant.from_utc(2023, 1, 1, 12, 0, 0),
        ),
        (
            StatsData(seeders=8, leechers=1, downloads=105),
            Instant.from_utc(2023, 1, 1, 13, 0, 0),
        ),
        (
            StatsData(seeders=5, leechers=0, downloads=110),
            Instant.from_utc(2023, 1, 1, 14, 0, 0),
        ),
        (
            StatsData(seeders=3, leechers=1, downloads=115),
            Instant.from_utc(2023, 1, 1, 15, 0, 0),
        ),
    ]

    for stats, timestamp in stats_data:
        temp_db.insert_stats(infohash, stats, timestamp)

    # Get recent stats (should be in descending order)
    recent = temp_db.get_recent_stats(infohash, limit=3)

    assert len(recent) == 3
    assert recent[0]["seeders"] == 3  # Most recent
    assert recent[1]["seeders"] == 5
    assert recent[2]["seeders"] == 8


def test_vacuum(temp_db):
    """Test database vacuum operation."""
    # This should not raise any errors
    temp_db.vacuum()


def test_indexes_exist(temp_db):
    """Test that required indexes exist."""
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = [
            "idx_stats_infohash",
            "idx_stats_timestamp",
            "idx_torrents_pubdate",
            "idx_torrents_status",
        ]

        for index in expected_indexes:
            assert index in indexes


def test_insert_duplicate_torrent(temp_db):
    """Test inserting duplicate torrent (should be ignored)."""
    torrent_data_1 = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="[Test] Anime Episode 01 [1080p].mkv",
        pubdate=Instant.from_utc(2023, 1, 1, 12, 0, 0),
        size_bytes=1000000000,
        nyaa_id=12345,
        trusted=True,
        remake=False,
        seeders=10,
        leechers=2,
        downloads=100,
        guessit_data={"title": "First"},
    )

    torrent_data_2 = TorrentData(
        infohash="abcdef1234567890abcdef1234567890abcdef12",
        filename="[Test] Anime Episode 01 [1080p].mkv",
        pubdate=Instant.from_utc(2023, 1, 1, 12, 0, 0),
        size_bytes=1000000000,
        nyaa_id=12345,
        trusted=True,
        remake=False,
        seeders=10,
        leechers=2,
        downloads=100,
        guessit_data={"title": "Second"},
    )

    # Insert first time
    temp_db.insert_torrent(torrent_data_1)

    # Insert duplicate (should be ignored)
    temp_db.insert_torrent(torrent_data_2)

    # Check only one record exists
    with temp_db.get_conn() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM torrents WHERE infohash = ?",
            (torrent_data_1.infohash,),
        )
        count = cursor.fetchone()["count"]

        assert count == 1

        # Check the guessit data is still from first insert
        cursor = conn.execute(
            "SELECT guessit_data FROM torrents WHERE infohash = ?",
            (torrent_data_1.infohash,),
        )
        row = cursor.fetchone()

        stored_guessit = json.loads(row["guessit_data"])
        assert stored_guessit["title"] == "First"
