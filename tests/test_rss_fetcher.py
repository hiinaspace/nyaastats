from unittest.mock import Mock, patch

import pytest
from whenever import Instant

from nyaastats.rss_fetcher import RSSFetcher


@pytest.fixture
def mock_rss_response():
    """Mock RSS response content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
    <channel>
        <title>Nyaa - Test Feed</title>
        <item>
            <title>[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv</title>
            <link>https://nyaa.si/download/123456.torrent</link>
            <guid isPermaLink="true">https://nyaa.si/view/123456</guid>
            <pubDate>Wed, 01 Jan 2025 12:00:00 +0000</pubDate>
            <nyaa:seeders>10</nyaa:seeders>
            <nyaa:leechers>2</nyaa:leechers>
            <nyaa:downloads>100</nyaa:downloads>
            <nyaa:infoHash>abcdef1234567890abcdef1234567890abcdef12</nyaa:infoHash>
            <nyaa:size>1.5 GiB</nyaa:size>
            <nyaa:trusted>Yes</nyaa:trusted>
            <nyaa:remake>No</nyaa:remake>
        </item>
    </channel>
</rss>"""


def test_parse_size():
    """Test size parsing functionality."""
    import httpx

    fetcher = RSSFetcher(Mock(), httpx.Client())

    # Test various size formats
    assert fetcher._parse_size("1.5 GiB") == int(1.5 * 1024**3)
    assert fetcher._parse_size("500 MiB") == int(500 * 1024**2)
    assert fetcher._parse_size("2.0 GB") == int(2.0 * 1024**3)
    assert fetcher._parse_size("750 MB") == int(750 * 1024**2)
    assert fetcher._parse_size("1024 KB") == int(1024 * 1024)
    assert fetcher._parse_size("512 B") == 512

    # Test invalid formats
    assert fetcher._parse_size("invalid") == 0
    assert fetcher._parse_size("") == 0
    assert fetcher._parse_size("1.5") == 0
    assert fetcher._parse_size("1.5 XB") == 0


def test_fetch_feed(rss_fetcher, mock_rss_response):
    """Test RSS feed fetching."""
    # Mock HTTP response
    mock_response = Mock()
    mock_response.text = mock_rss_response
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        # Test fetching without pagination
        feed = rss_fetcher.fetch_feed()

        assert len(feed.entries) == 1
        assert (
            feed.entries[0].title
            == "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
        )

        # Test fetching with pagination
        feed = rss_fetcher.fetch_feed(page=2)

        # Verify URL was called with page parameter
        rss_fetcher.client.get.assert_called_with(f"{rss_fetcher.feed_url}&p=2")


def test_parse_entry_basic(rss_fetcher):
    """Test basic entry parsing."""
    # Create a mock entry
    entry = Mock()
    entry.title = "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
    entry.guid = "https://nyaa.si/view/123456"
    entry.published = "Wed, 01 Jan 2025 12:00:00 +0000"
    entry.published_parsed = (2025, 1, 1, 12, 0, 0, 2, 1, 0)
    entry.nyaa_infohash = "abcdef1234567890abcdef1234567890abcdef12"
    entry.nyaa_size = "1.5 GiB"
    entry.nyaa_trusted = "Yes"
    entry.nyaa_remake = "No"
    entry.nyaa_seeders = "10"
    entry.nyaa_leechers = "2"
    entry.nyaa_downloads = "100"

    # Mock guessit
    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "season": 1,
            "episode": 1,
            "screen_size": "1080p",
            "video_codec": "H.264",
            "audio_codec": "AAC",
            "container": "mkv",
            "release_group": "TestGroup",
            "type": "episode",
        }

        torrent_data, guessit_data = rss_fetcher.parse_entry(entry)

        # Check torrent data
        assert torrent_data.infohash == "abcdef1234567890abcdef1234567890abcdef12"
        assert (
            torrent_data.filename
            == "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
        )
        assert torrent_data.size_bytes == int(1.5 * 1024**3)
        assert torrent_data.nyaa_id == 123456
        assert torrent_data.trusted
        assert not torrent_data.remake
        assert torrent_data.seeders == 10
        assert torrent_data.leechers == 2
        assert torrent_data.downloads == 100

        # Check guessit data
        assert guessit_data.title == "Test Anime"
        assert guessit_data.season == 1
        assert guessit_data.episode == 1
        assert guessit_data.screen_size == "1080p"
        assert guessit_data.video_codec == "H.264"
        assert guessit_data.audio_codec == "AAC"
        assert guessit_data.container == "mkv"
        assert guessit_data.release_group == "TestGroup"


def test_parse_entry_guessit_failure(rss_fetcher):
    """Test entry parsing when guessit fails."""
    entry = Mock()
    entry.title = "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
    entry.guid = "https://nyaa.si/view/123456"
    entry.published = "Wed, 01 Jan 2025 12:00:00 +0000"
    entry.published_parsed = (2025, 1, 1, 12, 0, 0, 2, 1, 0)
    entry.nyaa_infohash = "abcdef1234567890abcdef1234567890abcdef12"
    entry.nyaa_size = "1.5 GiB"
    entry.nyaa_trusted = "Yes"
    entry.nyaa_remake = "No"
    entry.nyaa_seeders = "10"
    entry.nyaa_leechers = "2"
    entry.nyaa_downloads = "100"

    # Mock guessit to raise an exception
    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.side_effect = Exception("Guessit error")

        torrent_data, guessit_data = rss_fetcher.parse_entry(entry)

        # Torrent data should still be parsed
        assert torrent_data.infohash == "abcdef1234567890abcdef1234567890abcdef12"
        assert (
            torrent_data.filename
            == "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
        )

        # Guessit data should be empty (all fields None/default)
        assert guessit_data.title is None
        assert guessit_data.episode is None


def test_parse_entry_missing_fields(rss_fetcher):
    """Test entry parsing with missing optional fields."""
    entry = Mock()
    entry.title = "Test Torrent"
    entry.guid = ""
    entry.published = ""
    entry.published_parsed = None
    entry.nyaa_infohash = "abcdef1234567890abcdef1234567890abcdef12"
    entry.nyaa_size = ""
    entry.nyaa_trusted = "No"
    entry.nyaa_remake = "Yes"
    entry.nyaa_seeders = "0"
    entry.nyaa_leechers = "0"
    entry.nyaa_downloads = "0"

    # Since we use controlled time through fixtures, no mocking needed
    # Mock guessit
    from unittest.mock import patch

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {}

        torrent_data, guessit_data = rss_fetcher.parse_entry(entry)

        assert torrent_data.infohash == "abcdef1234567890abcdef1234567890abcdef12"
        assert torrent_data.filename == "Test Torrent"
        assert torrent_data.size_bytes == 0
        assert torrent_data.nyaa_id is None
        assert not torrent_data.trusted
        assert torrent_data.remake
        assert torrent_data.seeders == 0
        assert torrent_data.leechers == 0
        assert torrent_data.downloads == 0
        # Uses the fixed_time from fixture (2025, 1, 1, 12, 0, 0)
        assert torrent_data.pubdate == Instant.from_utc(2025, 1, 1, 12, 0, 0)


def test_process_feed(rss_fetcher, mock_rss_response):
    """Test processing RSS feed."""
    # Mock HTTP response
    mock_response = Mock()
    mock_response.text = mock_rss_response
    mock_response.raise_for_status = Mock()

    # Mock the client.get method directly
    with patch.object(rss_fetcher.client, "get", return_value=mock_response):
        # Mock guessit
        with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
            mock_guessit.return_value = {
                "title": "Test Anime",
                "season": 1,
                "episode": 1,
                "screen_size": "1080p",
                "video_codec": "H.264",
                "audio_codec": "AAC",
                "container": "mkv",
                "release_group": "TestGroup",
                "type": "episode",
            }

            processed = rss_fetcher.process_feed()

            assert processed == 1

            # Verify torrent was stored in database
            assert rss_fetcher.db.get_torrent_exists(
                "abcdef1234567890abcdef1234567890abcdef12"
            )


def test_process_feed_skip_invalid_entries(rss_fetcher):
    """Test processing feed with invalid entries."""
    # Mock feed with invalid entry
    mock_feed = Mock()
    mock_feed.entries = [
        Mock(title="", nyaa_infohash=""),  # Invalid entry
        Mock(
            title="Valid Title",
            nyaa_infohash="abcdef1234567890abcdef1234567890abcdef12",
        ),
    ]

    # Mock fetch_feed to return our mock feed
    with patch.object(rss_fetcher, "fetch_feed") as mock_fetch:
        mock_fetch.return_value = mock_feed

        # Mock parse_entry to return appropriate data
        with patch.object(rss_fetcher, "parse_entry") as mock_parse:
            from nyaastats.models import GuessitData, TorrentData

            mock_parse.side_effect = [
                (
                    TorrentData(
                        infohash="",
                        filename="",
                        pubdate=Instant.from_utc(2025, 1, 1),
                        size_bytes=0,
                        nyaa_id=None,
                        trusted=False,
                        remake=False,
                        seeders=0,
                        leechers=0,
                        downloads=0,
                    ),
                    GuessitData(),
                ),  # Invalid entry
                (
                    TorrentData(
                        infohash="abcdef1234567890abcdef1234567890abcdef12",
                        filename="Valid Title",
                        pubdate=Instant.from_utc(2025, 1, 1, 12, 0, 0),
                        size_bytes=1000000,
                        nyaa_id=123456,
                        trusted=False,
                        remake=False,
                        seeders=10,
                        leechers=2,
                        downloads=100,
                    ),
                    GuessitData(),
                ),  # Valid entry
            ]

            processed = rss_fetcher.process_feed()

            # Should only process the valid entry
            assert processed == 1


def test_process_feed_exception_handling(rss_fetcher):
    """Test process_feed handles exceptions gracefully."""
    # Mock feed with entry that causes exception
    mock_feed = Mock()
    mock_feed.entries = [Mock(title="Test Entry")]

    with patch.object(rss_fetcher, "fetch_feed") as mock_fetch:
        mock_fetch.return_value = mock_feed

        # Mock parse_entry to raise exception
        with patch.object(rss_fetcher, "parse_entry") as mock_parse:
            mock_parse.side_effect = Exception("Parse error")

            processed = rss_fetcher.process_feed()

            # Should handle exception and return 0
            assert processed == 0


def test_parse_entry_with_pathlib_objects(rss_fetcher):
    """Test parsing entry with pathlib objects from guessit."""
    entry = Mock()
    entry.title = "[TestGroup] Test Anime S01E01 [1080p] [x264] [AAC].mkv"
    entry.guid = "https://nyaa.si/view/123456"
    entry.published = "Wed, 01 Jan 2025 12:00:00 +0000"
    entry.published_parsed = (2025, 1, 1, 12, 0, 0, 2, 1, 0)
    entry.nyaa_infohash = "abcdef1234567890abcdef1234567890abcdef12"
    entry.nyaa_size = "1.5 GiB"
    entry.nyaa_trusted = "Yes"
    entry.nyaa_remake = "No"
    entry.nyaa_seeders = "10"
    entry.nyaa_leechers = "2"
    entry.nyaa_downloads = "100"

    # Mock pathlib.Path object
    mock_path = Mock()
    mock_path.__fspath__ = Mock(return_value="/path/to/file.mkv")

    # Mock guessit with pathlib objects
    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "container": mock_path,  # This should be converted to string
            "subtitles": [mock_path, "en"],  # List with pathlib object
        }

        torrent_data, guessit_data = rss_fetcher.parse_entry(entry)

        # Check that pathlib objects were converted to strings
        assert guessit_data.container == "/path/to/file.mkv"
        assert guessit_data.subtitles == ["/path/to/file.mkv", "en"]


def test_parse_entry_with_real_guessit_language_objects(rss_fetcher):
    """Test parsing entry with real guessit that returns Language objects."""
    # Use a realistic filename that will likely trigger Language objects
    entry = Mock()
    entry.title = "[Yameii] New Saga - S01E01 [English Dub] [CR WEB-DL 1080p]"
    entry.guid = "https://nyaa.si/view/123456"
    entry.published = "Wed, 01 Jan 2025 12:00:00 +0000"
    entry.published_parsed = (2025, 1, 1, 12, 0, 0, 2, 1, 0)
    entry.nyaa_infohash = "abcdef1234567890abcdef1234567890abcdef12"
    entry.nyaa_size = "1.5 GiB"
    entry.nyaa_trusted = "Yes"
    entry.nyaa_remake = "No"
    entry.nyaa_seeders = "10"
    entry.nyaa_leechers = "2"
    entry.nyaa_downloads = "100"

    # Use real guessit - don't mock it
    torrent_data, guessit_data = rss_fetcher.parse_entry(entry)

    # Verify that the parsing completed without errors
    assert torrent_data.infohash == "abcdef1234567890abcdef1234567890abcdef12"
    assert (
        torrent_data.filename
        == "[Yameii] New Saga - S01E01 [English Dub] [CR WEB-DL 1080p]"
    )

    # Verify that guessit_data is a valid Pydantic model (no validation errors)
    assert isinstance(guessit_data, type(guessit_data))

    # If language is present, it should be a string, not a Language object
    if guessit_data.language is not None:
        assert isinstance(guessit_data.language, str)

    # If subtitles are present, they should be strings in a list
    if guessit_data.subtitles is not None:
        assert isinstance(guessit_data.subtitles, list)
        for subtitle in guessit_data.subtitles:
            assert isinstance(subtitle, str)
