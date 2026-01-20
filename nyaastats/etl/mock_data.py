"""Mock AniList data for testing without API access."""

from nyaastats.etl.anilist_client import AniListShow

# Mock shows matching the fake data generator
MOCK_FALL_2025_SHOWS = [
    AniListShow(
        id=1001,
        title_romaji="Dungeon Meshi Season 2",
        title_english="Delicious in Dungeon Season 2",
        synonyms=["Dungeon Meshi S2"],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#4a9eff",
        start_date=(2025, 10, 1),
        format="TV",
    ),
    AniListShow(
        id=1002,
        title_romaji="Frieren: Beyond Journey's End Season 2",
        title_english="Frieren Season 2",
        synonyms=["Frieren S2"],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#6366f1",
        start_date=(2025, 10, 1),
        format="TV",
    ),
    AniListShow(
        id=1003,
        title_romaji="Chainsaw Man Season 2",
        title_english="Chainsaw Man S2",
        synonyms=[],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#dc2626",
        start_date=(2025, 10, 1),
        format="TV",
    ),
    AniListShow(
        id=1004,
        title_romaji="Spy x Family Season 3",
        title_english="Spy Family S3",
        synonyms=["Spy x Family S3"],
        episodes=13,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#22c55e",
        start_date=(2025, 10, 1),
        format="TV",
    ),
    AniListShow(
        id=1005,
        title_romaji="My Hero Academia Season 8",
        title_english="Boku no Hero Academia S8",
        synonyms=["My Hero Academia S8"],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#eab308",
        start_date=(2025, 10, 1),
        format="TV",
    ),
]

MOCK_WINTER_2026_SHOWS = [
    AniListShow(
        id=2001,
        title_romaji="Solo Leveling Season 2",
        title_english="Solo Leveling S2",
        synonyms=[],
        episodes=12,
        status="RELEASING",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#8b5cf6",
        start_date=(2026, 1, 1),
        format="TV",
    ),
    AniListShow(
        id=2002,
        title_romaji="Demon Slayer Season 6",
        title_english="Kimetsu no Yaiba S6",
        synonyms=["Demon Slayer S6"],
        episodes=12,
        status="RELEASING",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#ec4899",
        start_date=(2026, 1, 1),
        format="TV",
    ),
    AniListShow(
        id=2003,
        title_romaji="The Apothecary Diaries Season 2",
        title_english="Kusuriya no Hitorigoto S2",
        synonyms=["Apothecary Diaries S2"],
        episodes=12,
        status="RELEASING",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#14b8a6",
        start_date=(2026, 1, 1),
        format="TV",
    ),
    AniListShow(
        id=2004,
        title_romaji="Kusuriya no Hitorigoto Season 2",
        title_english="The Apothecary Diaries S2",
        synonyms=[],
        episodes=12,
        status="RELEASING",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#f97316",
        start_date=(2026, 1, 1),
        format="TV",
    ),
    AniListShow(
        id=2005,
        title_romaji="Wind Breaker",
        title_english="Wind Breaker",
        synonyms=[],
        episodes=13,
        status="RELEASING",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color="#06b6d4",
        start_date=(2026, 1, 1),
        format="TV",
    ),
]


def get_mock_seasons_data() -> dict[str, list[AniListShow]]:
    """Get mock season data for testing.

    Returns:
        Dict mapping season name to list of shows
    """
    return {
        "Fall 2025": MOCK_FALL_2025_SHOWS,
        "Winter 2026": MOCK_WINTER_2026_SHOWS,
    }
