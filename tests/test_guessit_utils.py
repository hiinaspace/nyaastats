"""Tests for guessit utilities."""

from unittest.mock import Mock, patch

from nyaastats.guessit_utils import parse_guessit_safe
from nyaastats.models import GuessitData


def test_parse_guessit_safe_basic():
    """Test basic guessit parsing."""
    filename = "[TestGroup] Test Anime S01E01 [1080p].mkv"
    result = parse_guessit_safe(filename)

    assert isinstance(result, GuessitData)
    assert result.title == "Test Anime"
    assert result.season == 1
    assert result.episode == 1


def test_parse_guessit_safe_empty_filename():
    """Test parsing empty filename."""
    result = parse_guessit_safe("")
    assert isinstance(result, GuessitData)
    assert result.title is None


def test_parse_guessit_safe_none_filename():
    """Test parsing None filename."""
    result = parse_guessit_safe(None)
    assert isinstance(result, GuessitData)
    assert result.title is None


def test_parse_guessit_safe_language_object():
    """Test handling Language objects from guessit."""
    filename = "[TestGroup] Test Anime [English Dub].mkv"

    # Mock Language object
    mock_language = Mock()
    mock_language.__class__.__name__ = "Language"
    mock_language.__str__ = Mock(return_value="en")

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "language": mock_language,
        }

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        assert result.title == "Test Anime"
        assert result.language == "en"


def test_parse_guessit_safe_list_episode():
    """Test handling episode lists (e.g., batch releases)."""
    filename = "[TestGroup] Test Anime - 01 ~ 08 [BATCH].mkv"

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "episode": [1, 8],  # Batch episode range
        }

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        assert result.title == "Test Anime"
        assert result.episode is None  # Should be None for multi-episode batches


def test_parse_guessit_safe_single_episode_list():
    """Test handling single episode in list."""
    filename = "[TestGroup] Test Anime S01E01.mkv"

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "season": [1],  # Single season in list
            "episode": [1],  # Single episode in list
        }

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        assert result.title == "Test Anime"
        assert result.season == 1  # Should extract single value
        assert result.episode == 1  # Should extract single value


def test_parse_guessit_safe_path_object():
    """Test handling Path objects from guessit."""
    filename = "/path/to/[TestGroup] Test Anime.mkv"

    # Mock Path object
    mock_path = Mock()
    mock_path.__fspath__ = Mock(return_value="/path/to/file.mkv")

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.return_value = {
            "title": "Test Anime",
            "container": mock_path,
        }

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        assert result.title == "Test Anime"
        assert result.container == "/path/to/file.mkv"


def test_parse_guessit_safe_exception_handling():
    """Test handling guessit exceptions."""
    filename = "[TestGroup] Test Anime.mkv"

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        mock_guessit.side_effect = Exception("Guessit error")

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        assert result.title is None


def test_parse_guessit_safe_validation_error():
    """Test handling GuessitData validation errors."""
    filename = "[TestGroup] Test Anime.mkv"

    with patch("nyaastats.guessit_utils.guessit.guessit") as mock_guessit:
        # Return invalid data that will cause validation error
        mock_guessit.return_value = {
            "title": "Test Anime",
            "episode": "invalid_episode",  # Should be int
        }

        result = parse_guessit_safe(filename)

        assert isinstance(result, GuessitData)
        # Should fallback to empty GuessitData on validation error
        assert result.title is None
