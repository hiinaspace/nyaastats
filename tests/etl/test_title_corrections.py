"""Tests for title correction functionality."""

from nyaastats.etl.title_corrections import (
    TITLE_CORRECTIONS,
    apply_title_corrections,
)


class TestTitleCorrections:
    """Test suite for title corrections."""

    def test_apply_title_corrections_with_known_error(self):
        """Test that known guessit errors are corrected."""
        # Test the Oshi no Ko case
        result = apply_title_corrections("Oshi no")
        assert result == "oshi no ko"

        # Test case insensitivity
        result = apply_title_corrections("OSHI NO")
        assert result == "oshi no ko"

        result = apply_title_corrections("Oshi No")
        assert result == "oshi no ko"

    def test_apply_title_corrections_with_correct_title(self):
        """Test that correct titles are not modified."""
        result = apply_title_corrections("One Punch Man")
        assert result == "One Punch Man"

        result = apply_title_corrections("Spy x Family")
        assert result == "Spy x Family"

    def test_apply_title_corrections_with_none(self):
        """Test that None input returns None."""
        result = apply_title_corrections(None)
        assert result is None

    def test_apply_title_corrections_with_whitespace(self):
        """Test that whitespace is handled correctly."""
        result = apply_title_corrections("  oshi no  ")
        assert result == "oshi no ko"

    def test_title_corrections_dict_is_lowercase(self):
        """Test that all keys in TITLE_CORRECTIONS are lowercase."""
        for key in TITLE_CORRECTIONS.keys():
            assert key == key.lower(), f"Key '{key}' is not lowercase"
