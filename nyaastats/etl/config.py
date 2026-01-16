"""Configuration for ETL pipeline."""

from dataclasses import dataclass
from whenever import Instant


@dataclass
class SeasonConfig:
    """Configuration for a specific anime season."""

    name: str
    season: str  # "FALL" or "WINTER" for AniList query
    year: int
    start_date: Instant
    end_date: Instant


# Fall 2025 season configuration
FALL_2025 = SeasonConfig(
    name="Fall 2025",
    season="FALL",
    year=2025,
    start_date=Instant.from_utc(2025, 10, 1),
    end_date=Instant.from_utc(2025, 12, 31),
)

# Winter 2026 season configuration (in progress)
WINTER_2026 = SeasonConfig(
    name="Winter 2026",
    season="WINTER",
    year=2026,
    start_date=Instant.from_utc(2026, 1, 1),
    end_date=Instant.from_utc(2026, 3, 31),
)

# All seasons to process for MVP
MVP_SEASONS = [FALL_2025, WINTER_2026]


# Manual title overrides for fuzzy matching
# Maps torrent title variations to specific AniList IDs
TITLE_OVERRIDES: dict[str, int] = {
    # Add entries as needed during development
    # Example: "Boku no Hero": 123456,
}

# Fuzzy matching threshold (0-100)
# This will be tuned during implementation by inspecting match results
FUZZY_MATCH_THRESHOLD = 85

# Post-airing cutoff: track downloads for N weeks after final episode
POST_AIRING_WEEKS = 4

# AniList API configuration
ANILIST_API_URL = "https://graphql.anilist.co"
ANILIST_RATE_LIMIT_PER_MINUTE = 90
