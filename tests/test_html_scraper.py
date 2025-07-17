from unittest.mock import Mock

import pytest
from whenever import Instant

from nyaastats.html_scraper import HtmlScraper
from nyaastats.models import TorrentData


@pytest.fixture
def example_html():
    """Load the example HTML fixture."""
    with open("tests/fixtures/example.html", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def html_scraper(temp_db, fixed_time):
    """Create HtmlScraper instance with mocked HTTP client."""
    mock_client = Mock()
    return HtmlScraper(temp_db, mock_client, now_func=lambda: fixed_time)


def test_parse_html_page(html_scraper, example_html):
    """Test parsing HTML page with example fixture."""
    results = html_scraper.parse_html_page(example_html)

    # Should have parsed multiple torrents
    assert len(results) > 0

    # Check first result structure
    first_result = results[0]
    assert isinstance(first_result, TorrentData)

    # Check torrent data fields
    assert first_result.infohash
    assert first_result.filename
    assert isinstance(first_result.pubdate, Instant)
    assert first_result.size_bytes > 0
    assert first_result.nyaa_id is not None
    assert isinstance(first_result.trusted, bool)
    assert isinstance(first_result.remake, bool)
    assert first_result.seeders >= 0
    assert first_result.leechers >= 0
    assert first_result.downloads >= 0

    # Check guessit data is present and properly serialized
    assert first_result.guessit_data is not None
    assert isinstance(first_result.guessit_data, dict)


def test_parse_specific_torrent(html_scraper, example_html):
    """Test parsing specific torrent data from example HTML."""
    results = html_scraper.parse_html_page(example_html)

    # Find a specific torrent we know exists in the example
    # Looking for the first torrent in the example HTML
    torrent_data = None
    for result in results:
        if result.nyaa_id == 1993369:  # First torrent ID from example
            torrent_data = result
            break

    assert torrent_data is not None
    assert "Kijin Gentoushou" in torrent_data.filename
    assert torrent_data.infohash == "2481b33774f420c0387fe6c7d52de66a05afaf12"
    assert torrent_data.trusted  # success class
    assert not torrent_data.remake


def test_extract_nyaa_id(html_scraper):
    """Test extracting nyaa_id from view link."""
    test_cases = [
        ("/view/1994237", 1994237),
        ("/view/123456", 123456),
        ("/view/1994237#comments", 1994237),
    ]

    for href, expected_id in test_cases:
        result = html_scraper._extract_nyaa_id(href)
        assert result == expected_id


def test_extract_nyaa_id_invalid(html_scraper):
    """Test extracting nyaa_id with invalid input."""
    with pytest.raises(ValueError):
        html_scraper._extract_nyaa_id("/invalid/path")


def test_extract_infohash(html_scraper):
    """Test extracting infohash from magnet link."""
    magnet_url = "magnet:?xt=urn:btih:81d19980b33b96ab49dae00e5d75539c7b300e85&dn=test&tr=tracker"
    result = html_scraper._extract_infohash(magnet_url)
    assert result == "81d19980b33b96ab49dae00e5d75539c7b300e85"


def test_extract_infohash_invalid(html_scraper):
    """Test extracting infohash with invalid magnet link."""
    with pytest.raises(ValueError):
        html_scraper._extract_infohash("invalid_magnet_link")


def test_parse_size(html_scraper):
    """Test parsing size strings to bytes."""
    test_cases = [
        ("1.2 GiB", int(1.2 * 1024**3)),
        ("309.2 MiB", int(309.2 * 1024**2)),
        ("5.2 GiB", int(5.2 * 1024**3)),
        ("1.3 GiB", int(1.3 * 1024**3)),
        ("861.0 MiB", int(861.0 * 1024**2)),
        ("1024 KiB", 1024 * 1024),
        ("1 B", 1),
        ("100 B", 100),
    ]

    for size_str, expected_bytes in test_cases:
        result = html_scraper._parse_size(size_str)
        assert result == expected_bytes


def test_parse_size_invalid(html_scraper):
    """Test parsing invalid size strings."""
    with pytest.raises(ValueError):
        html_scraper._parse_size("invalid size")


def test_fetch_page(html_scraper):
    """Test fetching HTML page."""
    mock_response = Mock()
    mock_response.text = "<html>test</html>"
    html_scraper.client.get.return_value = mock_response

    result = html_scraper.fetch_page(page=1)

    assert result == "<html>test</html>"
    html_scraper.client.get.assert_called_once_with(
        "https://nyaa.si", params={"c": "1_2", "f": "0", "p": "1"}
    )


def test_fetch_page_error(html_scraper):
    """Test fetching HTML page with HTTP error."""
    html_scraper.client.get.side_effect = Exception("HTTP Error")

    with pytest.raises(Exception, match="HTTP Error"):
        html_scraper.fetch_page(page=1)


def test_process_page(html_scraper, example_html):
    """Test processing a complete page."""
    # Mock the fetch_page method
    html_scraper.fetch_page = Mock(return_value=example_html)

    # Mock database methods
    html_scraper.db.get_torrent_exists = Mock(return_value=False)
    html_scraper.db.insert_torrent = Mock()

    result = html_scraper.process_page(page=1)

    # Should have processed some torrents
    assert result > 0

    # Check that database methods were called
    assert html_scraper.db.get_torrent_exists.called
    assert html_scraper.db.insert_torrent.called


def test_process_page_existing_torrents(html_scraper, example_html):
    """Test processing page with existing torrents."""
    # Mock the fetch_page method
    html_scraper.fetch_page = Mock(return_value=example_html)

    # Mock database to always return True (torrent exists)
    html_scraper.db.get_torrent_exists = Mock(return_value=True)
    html_scraper.db.insert_torrent = Mock()

    result = html_scraper.process_page(page=1)

    # Should have processed 0 new torrents
    assert result == 0

    # Check that insert_torrent was not called
    assert not html_scraper.db.insert_torrent.called


def test_parse_torrent_with_comments(html_scraper, example_html):
    """Test parsing torrents that have comment counts."""
    results = html_scraper.parse_html_page(example_html)

    # Find a torrent with comments (we know 1993179 has 7 comments)
    torrent_data = None
    for result in results:
        if result.nyaa_id == 1993179:
            torrent_data = result
            break

    assert torrent_data is not None
    # Should have the actual torrent filename, not "7 comments"
    assert "[Some-Stuffs] City the Animation 01" in torrent_data.filename
    assert torrent_data.filename != "7 comments"  # Should not be comment text
    assert torrent_data.infohash  # Should have valid infohash


def test_parse_table_row_trusted_remake_status(html_scraper, example_html):
    """Test parsing row classes for trusted and remake status."""
    results = html_scraper.parse_html_page(example_html)

    # Should have a mix of trusted/remake statuses
    statuses = [(r.trusted, r.remake) for r in results]

    # Check that we have at least one trusted torrent (success class)
    assert any(trusted for trusted, remake in statuses)

    # Check that we have at least one remake torrent (danger class)
    assert any(remake for trusted, remake in statuses)


def test_parse_empty_html(html_scraper):
    """Test parsing empty or invalid HTML."""
    empty_html = "<html><body></body></html>"
    results = html_scraper.parse_html_page(empty_html)
    assert results == []


def test_parse_html_no_table(html_scraper):
    """Test parsing HTML without torrent table."""
    html_without_table = "<html><body><p>No table here</p></body></html>"
    results = html_scraper.parse_html_page(html_without_table)
    assert results == []
