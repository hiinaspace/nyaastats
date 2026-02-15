"""AniList GraphQL API client."""

import asyncio
import logging
from dataclasses import dataclass

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

from .config import ANILIST_API_URL, MOVIE_DATE_RANGE, MOVIE_FORMATS, SeasonConfig

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
    cover_image_url: str | None  # Large size cover image
    cover_image_color: str | None  # Dominant color hex
    start_date: tuple[int | None, int | None, int | None] | None  # (year, month, day)
    format: str | None  # TV, TV_SHORT, MOVIE, OVA, etc.


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
        self._client = Client(
            transport=self._transport, fetch_schema_from_transport=False
        )
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
                  format
                  startDate {
                    year
                    month
                    day
                  }
                  airingSchedule {
                    nodes {
                      episode
                      airingAt
                    }
                  }
                  coverImage {
                    large
                    medium
                    color
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
            logger.info(f"Fetching {season_config.name} anime, page {page}...")

            variables = {
                "season": season_config.season,
                "seasonYear": season_config.year,
                "page": page,
                "perPage": per_page,
            }

            # Retry logic for transient failures
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = await self._session.execute(
                        query, variable_values=variables
                    )
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"AniList API error (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"AniList API failed after {max_retries} attempts: {e}"
                        )
                        raise
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
            # Sleep between pages to be respectful
            await asyncio.sleep(1.0)  # Conservative rate: 60 requests per minute

        logger.info(f"Fetched {len(shows)} shows for {season_config.name}")
        return shows

    async def get_movies_by_date_range(
        self,
        start_date: tuple[int, int, int],
        end_date: tuple[int, int, int],
        formats: list[str] | None = None,
    ) -> list[AniListShow]:
        """Query AniList for movies/specials in a date range.

        Args:
            start_date: (year, month, day) tuple for range start
            end_date: (year, month, day) tuple for range end
            formats: AniList format types to include (default: MOVIE_FORMATS)

        Returns:
            List of shows filtered to single-episode entries
        """
        if formats is None:
            formats = MOVIE_FORMATS

        # AniList uses YYYYMMDD integer format for fuzzy dates
        start_int = start_date[0] * 10000 + start_date[1] * 100 + start_date[2]
        end_int = end_date[0] * 10000 + end_date[1] * 100 + end_date[2]

        query = gql(
            """
            query ($formats: [MediaFormat!], $startDate: FuzzyDateInt, $endDate: FuzzyDateInt, $page: Int!, $perPage: Int!) {
              Page(page: $page, perPage: $perPage) {
                pageInfo {
                  hasNextPage
                  currentPage
                }
                media(type: ANIME, format_in: $formats, startDate_greater: $startDate, startDate_lesser: $endDate) {
                  id
                  title {
                    romaji
                    english
                    native
                  }
                  synonyms
                  episodes
                  status
                  format
                  startDate {
                    year
                    month
                    day
                  }
                  airingSchedule {
                    nodes {
                      episode
                      airingAt
                    }
                  }
                  coverImage {
                    large
                    medium
                    color
                  }
                }
              }
            }
            """
        )

        shows = []
        page = 1
        per_page = 50

        while True:
            logger.info(f"Fetching movies (formats={formats}), page {page}...")

            variables = {
                "formats": formats,
                "startDate": start_int,
                "endDate": end_int,
                "page": page,
                "perPage": per_page,
            }

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = await self._session.execute(
                        query, variable_values=variables
                    )
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.warning(
                            f"AniList API error (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"AniList API failed after {max_retries} attempts: {e}"
                        )
                        raise

            page_data = result["Page"]

            for media in page_data["media"]:
                show = self._parse_show(media)
                # Post-filter: only keep single-episode entries (movies/specials)
                if show.episodes is None or show.episodes <= 1:
                    shows.append(show)

            if not page_data["pageInfo"]["hasNextPage"]:
                break

            page += 1
            await asyncio.sleep(1.0)

        logger.info(f"Fetched {len(shows)} movies/specials")
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
        cover_image = media.get("coverImage") or {}
        start_date_raw = media.get("startDate") or {}

        # Parse start date as tuple
        start_date = None
        if start_date_raw.get("year"):
            start_date = (
                start_date_raw.get("year"),
                start_date_raw.get("month"),
                start_date_raw.get("day"),
            )

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
            cover_image_url=cover_image.get("large"),
            cover_image_color=cover_image.get("color"),
            start_date=start_date,
            format=media.get("format"),
        )


async def fetch_all_seasons(
    seasons: list[SeasonConfig],
) -> dict[str, list[AniListShow]]:
    """Fetch anime for multiple seasons.

    Args:
        seasons: List of season configurations

    Returns:
        Dict mapping season name to list of shows
    """
    result = {}

    async with AniListClient() as client:
        for i, season in enumerate(seasons):
            shows = await client.get_season_anime(season)
            result[season.name] = shows

            # Sleep between seasons to avoid rate limiting
            if i < len(seasons) - 1:
                logger.info(
                    "Sleeping 2 seconds before next season to respect rate limits..."
                )
                await asyncio.sleep(2.0)

    return result


async def fetch_movies(
    start_date: tuple[int, int, int] | None = None,
    end_date: tuple[int, int, int] | None = None,
) -> list[AniListShow]:
    """Fetch movies/specials from AniList for a date range.

    Args:
        start_date: (year, month, day) tuple, defaults to MOVIE_DATE_RANGE start
        end_date: (year, month, day) tuple, defaults to MOVIE_DATE_RANGE end

    Returns:
        List of movie/special shows
    """
    if start_date is None:
        dt = MOVIE_DATE_RANGE[0].py_datetime()
        start_date = (dt.year, dt.month, dt.day)
    if end_date is None:
        dt = MOVIE_DATE_RANGE[1].py_datetime()
        end_date = (dt.year, dt.month, dt.day)

    async with AniListClient() as client:
        return await client.get_movies_by_date_range(start_date, end_date)
