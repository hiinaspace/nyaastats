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
# Maps normalized torrent title to specific AniList IDs
# Use scripts/anilist_lookup.py to find IDs for new overrides
TITLE_OVERRIDES: dict[str, int] = {
    # Oshi no Ko Season 3 (guessit parses as "Oshi no", correction to "Oshi no ko"
    # doesn't match well enough to "[Oshi no Ko] 3rd Season")
    "oshi no ko": 182587,  # [Oshi no Ko] 3rd Season (Winter 2026)
    # Yuusha Kei ni Shosu - Long subtitle prevents fuzzy match (score 49 < 85)
    "yuushakei ni shosu": 167152,  # Sentenced to Be a Hero (Winter 2026)
    # Spy x Family - "spy x family" scores 73 vs "Spy x Family Season 3" (below 85)
    "spy x family": 177937,  # Spy x Family Season 3 (Fall 2025)
    # Jujutsu Kaisen - "jujutsu kaisen" scores 55 vs long AniList S3 title (below 85)
    "jujutsu kaisen": 172463,  # Jujutsu Kaisen S3: The Culling Game Part 1 (Winter 2026)
    # Jigokuraku S2 - normalized "jigokuraku" doesn't match "Jigokuraku 2nd Season"
    "jigokuraku": 166613,  # Jigokuraku 2nd Season (Winter 2026)
    # Mushoku no Eiyuu - long subtitle on AniList prevents fuzzy match
    "mushoku no eiyuu": 169969,  # Hero Without a Class (Fall 2025)
    # Mikata ga Yowasugite... - extremely long AniList title
    "mikata ga yowasugite hojo mahou": 188487,  # Banished Court Magician (Fall 2025)
    # Akujiki Reijou - extremely long AniList title
    "akujiki reijou to kyouketsu koushaku": 183291,  # Pass the Monster Meat (Fall 2025)
    # Enen no Shouboutai S3 - guessit drops episode number, season=3 episode=null
    "enen no shouboutai": 179062,  # Fire Force S3 Part 2 (Winter 2026)
    # Kaguya-sama - subtitle stripping matches this but override is more reliable
    "kaguyasama wa kokurasetai": 194884,  # Kaguya-sama: Otona e no Kaidan (Fall 2025)
    # Kizoku Tensei - subtitle stripping would help but "Kizoku Tensei" alone is ambiguous
    "kizoku tensei": 185993,  # Noble Reincarnation (Winter 2026)
}

# Episode-to-season mappings for continuing series with continuous numbering
# Maps normalized title -> list of (min_ep, max_ep, anilist_id) tuples
# Used for shows like "Spy x Family" where ep 38 needs to map to Season 3
EPISODE_SEASON_MAPPINGS: dict[str, list[tuple[int, int, int]]] = {
    "spy x family": [
        # Some release groups use continuous numbering across seasons
        # Only mapping Season 3 (Fall 2025) since earlier seasons aren't tracked
        (26, 50, 177937),  # Season 3 (Fall 2025) - eps 26+ map to S3
    ],
    "jujutsu kaisen": [
        # Continuous numbering across seasons
        # Only mapping Season 3 (Winter 2026) since earlier seasons aren't tracked
        (48, 75, 172463),  # Season 3: The Culling Game Part 1 (Winter 2026)
    ],
}

# Titles to exclude from the unmatched report (normalized).
# These are intentionally untracked — not bugs in matching.
IGNORED_TITLES: set[str] = {
    # Summer 2025 shows — scraper started mid-June so data is incomplete
    "gachiakuta",  # Gachiakuta (Summer 2025, AniList 178025)
    "silent witch",  # Secrets of the Silent Witch (Summer 2025, AniList 179966)
    "secrets of the silent witch",
    # Ongoing long-running series outside tracked seasons
    "one piece",  # ONE PIECE (ongoing since 1999, AniList 21)
    # Movies — not tracked yet (may add separate movie display later)
    "demon slayer kimetsu no yaiba infinity castle",
    "kimetsu no yaiba",  # Movie releases parsed without "Infinity Castle"
    "chainsaw man the movie reze arc",
    "gekijouban chainsaw man reze hen",
    "chainsaw man movie rezehen",  # "Chainsaw Man Movie: Reze-hen" after normalization
    "chainsaw man the movie",  # "Chainsaw Man: The Movie" without subtitle
}

# Fuzzy matching threshold (0-100)
# This will be tuned during implementation by inspecting match results
FUZZY_MATCH_THRESHOLD = 85

# Post-airing cutoff: track downloads for N weeks after final episode
POST_AIRING_WEEKS = 4

# AniList API configuration
ANILIST_API_URL = "https://graphql.anilist.co"
ANILIST_RATE_LIMIT_PER_MINUTE = 90
