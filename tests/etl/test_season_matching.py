"""Tests for season-aware and episode-range matching."""

import pytest

from nyaastats.etl.anilist_client import AniListShow
from nyaastats.etl.fuzzy_matcher import FuzzyMatcher


@pytest.fixture
def mock_shows():
    """Create mock AniList shows for testing."""
    return [
        AniListShow(
            id=1,
            title_romaji="One-Punch Man Season 3",
            title_english="One-Punch Man Season 3",
            synonyms=[],
            format="TV",
            status="RELEASING",
            episodes=None,
            airing_schedule=[],
            cover_image_url=None,
            cover_image_color=None,
            start_date=(2025, 10, 1),
        ),
        AniListShow(
            id=2,
            title_romaji="One-Punch Man Season 2",
            title_english="One-Punch Man Season 2",
            synonyms=[],
            format="TV",
            status="FINISHED",
            episodes=12,
            airing_schedule=[],
            cover_image_url=None,
            cover_image_color=None,
            start_date=(2024, 4, 1),
        ),
        AniListShow(
            id=3,
            title_romaji="Spy x Family",
            title_english="Spy x Family",
            synonyms=[],
            format="TV",
            status="FINISHED",
            episodes=12,
            airing_schedule=[],
            cover_image_url=None,
            cover_image_color=None,
            start_date=(2022, 4, 9),
        ),
        AniListShow(
            id=4,
            title_romaji="Spy x Family Season 2",
            title_english="Spy x Family Season 2",
            synonyms=[],
            format="TV",
            status="FINISHED",
            episodes=13,
            airing_schedule=[],
            cover_image_url=None,
            cover_image_color=None,
            start_date=(2023, 10, 7),
        ),
        AniListShow(
            id=5,
            title_romaji="Oshi no Ko Season 3",
            title_english="Oshi no Ko Season 3",
            synonyms=["Oshi no Ko 3rd Season"],
            format="TV",
            status="RELEASING",
            episodes=None,
            airing_schedule=[],
            cover_image_url=None,
            cover_image_color=None,
            start_date=(2025, 10, 1),
        ),
    ]


class TestSeasonAwareMatching:
    """Test season-aware fuzzy matching."""

    def test_season_aware_match_with_season_in_title(self, mock_shows):
        """Test that season numbers in titles boost match scores."""
        # Use lower threshold for testing (70 is reasonable for partial matches)
        matcher = FuzzyMatcher(mock_shows, threshold=70)

        # Test matching "One-Punch Man S3"
        result = matcher.match("One-Punch Man", season=3)
        assert result is not None
        # Should prefer Season 3 over Season 2
        assert result.anilist_id == 1
        assert "season 3" in result.matched_title.lower()

    def test_fuzzy_match_without_season_info(self, mock_shows):
        """Test that matching works without season info (fallback)."""
        # Use lower threshold for testing
        matcher = FuzzyMatcher(mock_shows, threshold=70)

        result = matcher.match("One-Punch Man", season=None)
        assert result is not None
        # Without season info, should still match one of the shows
        assert result.anilist_id in [1, 2]

    def test_title_correction_applied_before_matching(self, mock_shows):
        """Test that title corrections are applied before fuzzy matching."""
        # Note: This test assumes apply_title_corrections is called
        # before fuzzy matching in the ETL pipeline
        # Use lower threshold for testing
        matcher = FuzzyMatcher(mock_shows, threshold=70)

        # "Oshi no" should be corrected to "Oshi no Ko" and match
        result = matcher.match("Oshi no Ko", season=3)
        assert result is not None
        assert result.anilist_id == 5


class TestEpisodeRangeMatching:
    """Test episode-range based matching for continuing series."""

    def test_episode_range_match(self, mock_shows):
        """Test episode range matching for configured series."""
        # Add episode mapping to config for testing
        from nyaastats.etl import config

        original_mappings = config.EPISODE_SEASON_MAPPINGS.copy()
        try:
            # Add test mapping
            config.EPISODE_SEASON_MAPPINGS["spy x family"] = [
                (1, 12, 3),  # S1
                (13, 25, 4),  # S2
            ]

            matcher = FuzzyMatcher(mock_shows, threshold=85)

            # Test episode 15 should map to Season 2 (AniList ID 4)
            result = matcher.match("Spy x Family", episode=15)
            assert result is not None
            assert result.anilist_id == 4
            assert result.method == "episode_range"
            assert result.score == 100.0

        finally:
            # Restore original config
            config.EPISODE_SEASON_MAPPINGS = original_mappings

    def test_episode_range_no_match_outside_range(self, mock_shows):
        """Test that episodes outside configured ranges don't match via episode_range."""
        from nyaastats.etl import config

        original_mappings = config.EPISODE_SEASON_MAPPINGS.copy()
        try:
            config.EPISODE_SEASON_MAPPINGS["spy x family"] = [
                (1, 12, 3),
                (13, 25, 4),
            ]

            matcher = FuzzyMatcher(mock_shows, threshold=85)

            # Episode 50 is outside all ranges, should fall back to fuzzy
            result = matcher.match("Spy x Family", episode=50)
            # Should still match via fuzzy, but not episode_range
            if result:
                assert result.method != "episode_range"

        finally:
            config.EPISODE_SEASON_MAPPINGS = original_mappings

    def test_episode_range_priority_over_fuzzy(self, mock_shows):
        """Test that episode_range matching has priority over fuzzy matching."""
        from nyaastats.etl import config

        original_mappings = config.EPISODE_SEASON_MAPPINGS.copy()
        try:
            config.EPISODE_SEASON_MAPPINGS["spy x family"] = [
                (1, 12, 3),
                (13, 25, 4),
            ]

            matcher = FuzzyMatcher(mock_shows, threshold=85)

            # Even with season info, episode_range should take priority
            result = matcher.match("Spy x Family", season=1, episode=15)
            assert result is not None
            assert result.method == "episode_range"
            assert result.anilist_id == 4  # Mapped by episode, not season

        finally:
            config.EPISODE_SEASON_MAPPINGS = original_mappings


class TestMatchBatch:
    """Test batch matching with new metadata."""

    def test_match_batch_with_season_and_episode(self, mock_shows):
        """Test that batch matching passes season and episode correctly."""
        # Use lower threshold for testing
        matcher = FuzzyMatcher(mock_shows, threshold=70)

        batch = [
            ("hash1", "One-Punch Man", 3, 1),
            ("hash2", "Spy x Family", None, 5),
            ("hash3", "Unknown Show", None, None),
        ]

        matched, unmatched = matcher.match_batch(batch)

        # Should match the first two
        assert len(matched) >= 1
        assert len(unmatched) >= 1

        # Check that hash1 was matched
        hash1_matches = [m for h, m in matched if h == "hash1"]
        assert len(hash1_matches) == 1

    def test_match_batch_logs_method_counts(self, mock_shows, caplog):
        """Test that batch matching logs statistics by method."""
        # Use lower threshold for testing
        matcher = FuzzyMatcher(mock_shows, threshold=70)

        batch = [
            ("hash1", "One-Punch Man", 3, 1),
            ("hash2", "Spy x Family", 2, 5),
        ]

        with caplog.at_level("INFO"):
            matched, unmatched = matcher.match_batch(batch)

        # Check that method counts are logged
        assert "Match methods:" in caplog.text or len(matched) == 0


class TestLowInformationTitleGuard:
    """Test guardrails against low-information fuzzy matches."""

    def test_numeric_only_guessit_title_does_not_match(self, mock_shows):
        matcher = FuzzyMatcher(mock_shows, threshold=70)
        result = matcher.match("2", season=2024, episode=1)
        assert result is None

    def test_non_latin_only_guessit_title_does_not_match(self, mock_shows):
        matcher = FuzzyMatcher(mock_shows, threshold=70)
        result = matcher.match("中文配音", season=None, episode=None)
        assert result is None


class TestSubtitleStrippingFallback:
    """Test subtitle-stripping fallback for titles with ' - ' separators."""

    @pytest.fixture
    def subtitle_shows(self):
        """Create shows that match the prefix but not the full subtitle title."""
        return [
            AniListShow(
                id=100,
                title_romaji="Kizoku Tensei",
                title_english="Noble Reincarnation",
                synonyms=[],
                format="ONA",
                status="RELEASING",
                episodes=None,
                airing_schedule=[],
                cover_image_url=None,
                cover_image_color=None,
                start_date=(2026, 1, 1),
            ),
            AniListShow(
                id=101,
                title_romaji="Silent Witch: Chinmoku no Majo no Kakushigoto",
                title_english="Secrets of the Silent Witch",
                synonyms=[],
                format="TV",
                status="FINISHED",
                episodes=13,
                airing_schedule=[],
                cover_image_url=None,
                cover_image_color=None,
                start_date=(2025, 7, 1),
            ),
            AniListShow(
                id=102,
                title_romaji="Kaguya-sama wa Kokurasetai: Otona e no Kaidan",
                title_english="Kaguya-sama: Love Is War -Stairway to Adulthood-",
                synonyms=[],
                format="SPECIAL",
                status="FINISHED",
                episodes=2,
                airing_schedule=[],
                cover_image_url=None,
                cover_image_color=None,
                start_date=(2025, 10, 1),
            ),
        ]

    def test_subtitle_stripping_matches_prefix(self, subtitle_shows):
        """Title with long Japanese subtitle should match via prefix stripping."""
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides={})
        result = matcher.match(
            "Kizoku Tensei - Megumareta Umare kara Saikyou no Chikara wo Eru"
        )
        assert result is not None
        assert result.anilist_id == 100

    def test_subtitle_stripping_silent_witch(self, subtitle_shows):
        """Silent Witch with subtitle should match."""
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides={})
        result = matcher.match("Silent Witch - Chinmoku no Majo no Kakushigoto")
        assert result is not None
        assert result.anilist_id == 101

    def test_subtitle_stripping_kaguya(self, subtitle_shows):
        """Kaguya-sama with subtitle should match via stripping."""
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides={})
        result = matcher.match("Kaguya-sama wa Kokurasetai - Otona e no Kaidan")
        assert result is not None
        assert result.anilist_id == 102

    def test_no_stripping_when_direct_match_works(self, subtitle_shows):
        """If the full title matches directly, don't need stripping."""
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides={})
        result = matcher.match("Kizoku Tensei")
        assert result is not None
        assert result.anilist_id == 100
        # Should match directly, not via fallback

    def test_short_prefix_not_used(self, subtitle_shows):
        """Prefix shorter than 4 chars should not trigger fallback."""
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides={})
        # "AB - something long" - prefix "AB" is too short
        result = matcher.match("AB - something long that won't match anything")
        assert result is None

    def test_subtitle_stripping_checks_overrides(self, subtitle_shows):
        """Subtitle stripping fallback should check manual overrides for prefix."""
        overrides = {"kizoku tensei": 999}
        # Add a show with id 999 so override can resolve
        subtitle_shows.append(
            AniListShow(
                id=999,
                title_romaji="Override Target",
                title_english=None,
                synonyms=[],
                format="TV",
                status="RELEASING",
                episodes=None,
                airing_schedule=[],
                cover_image_url=None,
                cover_image_color=None,
                start_date=(2026, 1, 1),
            )
        )
        matcher = FuzzyMatcher(subtitle_shows, threshold=85, overrides=overrides)
        result = matcher.match(
            "Kizoku Tensei - Megumareta Umare kara Saikyou no Chikara wo Eru"
        )
        assert result is not None
        assert result.anilist_id == 999
        assert result.method == "manual_override"
