"""AniList GraphQL API client."""

import asyncio
import logging
from dataclasses import dataclass

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from .config import ANILIST_API_URL, SeasonConfig

logger = logging.getLogger(__name__)


@dataclass
class AniListShow:
    """Metadata from AniList API."""

    id: int
    title_romaji: str
    title_english: str | None
    synonyms: list[str]
    episodes: int | None
    status: str
    airing_schedule: list[tuple[int, int]]  # (episode, unix_timestamp)


class AniListClient:
    """Client for querying AniList GraphQL API."""

    def __init__(self, api_url: str = ANILIST_API_URL):
        """Initialize AniList client.

        Args:
            api_url: AniList GraphQL endpoint URL
        """
        self.api_url = api_url
        self._transport = None
        self._client = None
        self._session = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._transport = AIOHTTPTransport(url=self.api_url)
        self._client = Client(transport=self._transport, fetch_schema_from_transport=False)
        self._session = await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
        if self._transport:
            await self._transport.close()

    async def get_season_anime(self, season_config: SeasonConfig) -> list[AniListShow]:
        """Query AniList for all anime in a given season.

        Args:
            season_config: Season configuration

        Returns:
            List of shows with metadata
        """
        query = gql(
            """
            query ($season: MediaSeason!, $seasonYear: Int!, $page: Int!, $perPage: Int!) {
              Page(page: $page, perPage: $perPage) {
                pageInfo {
                  hasNextPage
                  currentPage
                }
                media(season: $season, seasonYear: $seasonYear, type: ANIME) {
                  id
                  title {
                    romaji
                    english
                    native
                  }
                  synonyms
                  episodes
                  status
                  airingSchedule {
                    nodes {
                      episode
                      airingAt
                    }
                  }
                }
              }
            }
            """
        )

        shows = []
        page = 1
        per_page = 50  # AniList default

        while True:
            logger.info(
                f"Fetching {season_config.name} anime, page {page}..."
            )

            variables = {
                "season": season_config.season,
                "seasonYear": season_config.year,
                "page": page,
                "perPage": per_page,
            }

            result = await self._session.execute(query, variable_values=variables)
            page_data = result["Page"]

            # Parse shows from this page
            for media in page_data["media"]:
                show = self._parse_show(media)
                shows.append(show)

            # Check if there are more pages
            if not page_data["pageInfo"]["hasNextPage"]:
                break

            page += 1

            # Rate limiting: AniList allows 90 req/min
            # Sleep briefly between pages to be respectful
            await asyncio.sleep(0.7)  # ~85 requests per minute

        logger.info(
            f"Fetched {len(shows)} shows for {season_config.name}"
        )
        return shows

    def _parse_show(self, media: dict) -> AniListShow:
        """Parse AniList media object into AniListShow.

        Args:
            media: Raw media dict from AniList API

        Returns:
            Parsed show metadata
        """
        title = media["title"]
        airing_schedule = media.get("airingSchedule", {}).get("nodes", [])

        return AniListShow(
            id=media["id"],
            title_romaji=title.get("romaji", ""),
            title_english=title.get("english"),
            synonyms=media.get("synonyms", []),
            episodes=media.get("episodes"),
            status=media.get("status", ""),
            airing_schedule=[
                (node["episode"], node["airingAt"]) for node in airing_schedule
            ],
        )


async def fetch_all_seasons(seasons: list[SeasonConfig]) -> dict[str, list[AniListShow]]:
    """Fetch anime for multiple seasons.

    Args:
        seasons: List of season configurations

    Returns:
        Dict mapping season name to list of shows
    """
    result = {}

    async with AniListClient() as client:
        for season in seasons:
            shows = await client.get_season_anime(season)
            result[season.name] = shows

    return result
