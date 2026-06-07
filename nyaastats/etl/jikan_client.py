"""Jikan (unofficial MyAnimeList) API client with persistent caching.

Fetches MyAnimeList score/ranking data keyed by AniList's ``idMal`` and caches
it in the ``external_ratings`` table so reruns don't re-hit the API. Jikan v4 is
rate limited to 3 req/s and 60 req/min; we sleep between requests to stay under
both caps.
"""

import asyncio
import logging
from typing import Any

import httpx
from whenever import Instant

from .anilist_client import AniListShow
from .config import EXTERNAL_RATING_TTL_DAYS, JIKAN_API_URL, JIKAN_RATE_LIMIT

logger = logging.getLogger(__name__)

SOURCE = "mal"

# Fields we capture from the Jikan /anime/{id} payload.
_CAPTURED_FIELDS = ("score", "scored_by", "rank", "popularity", "members", "favorites")


class JikanClient:
    """Rate-limited client for the Jikan v4 REST API."""

    def __init__(
        self,
        api_url: str = JIKAN_API_URL,
        rate_limit: float = JIKAN_RATE_LIMIT,
    ):
        self.api_url = api_url.rstrip("/")
        self.rate_limit = rate_limit
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "JikanClient":
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()

    async def get_anime(self, mal_id: int) -> dict[str, Any] | None:
        """Fetch and extract rating fields for a MyAnimeList id.

        Returns:
            Dict of captured fields, or None if the anime was not found (404).
        """
        assert self._client is not None, "JikanClient must be used as a context manager"
        url = f"{self.api_url}/anime/{mal_id}"

        max_retries = 4
        for attempt in range(max_retries):
            try:
                resp = await self._client.get(url)
                if resp.status_code == 404:
                    logger.warning(f"Jikan: anime {mal_id} not found (404)")
                    return None
                if resp.status_code == 429:
                    # Rate limited; back off and retry.
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Jikan: rate limited on {mal_id}, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json().get("data", {})
                return {field: data.get(field) for field in _CAPTURED_FIELDS}
            except (httpx.HTTPError, ValueError) as e:
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        f"Jikan error for {mal_id} "
                        f"(attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Jikan failed for {mal_id} after {max_retries}: {e}")
                    return None
        return None


def _is_stale(fetched_at: str, ttl_days: int, now: Instant) -> bool:
    """Return True if a cached row is older than the TTL (or unparseable)."""
    try:
        age_seconds = now.timestamp() - Instant.parse_common_iso(fetched_at).timestamp()
        return age_seconds >= ttl_days * 86400
    except Exception:
        return True


async def fetch_mal_ratings(
    db: Any,
    shows: list[AniListShow],
    ttl_days: int = EXTERNAL_RATING_TTL_DAYS,
    now_func=Instant.now,
) -> dict[int, dict[str, Any]]:
    """Fetch MAL ratings for shows, using and updating the DB cache.

    Only shows whose cache entry is missing or older than ``ttl_days`` are
    re-fetched. Shows without an ``id_mal`` are skipped.

    Args:
        db: Database instance with get_external_ratings/upsert_external_rating
        shows: AniList shows (need ``id`` and ``id_mal``)
        ttl_days: Re-fetch entries older than this
        now_func: Callable returning current Instant (for testing)

    Returns:
        Dict mapping anilist_id to the captured MAL payload.
    """
    now = now_func()
    cache = db.get_external_ratings(SOURCE)

    # Determine which shows need a fresh fetch.
    to_fetch: list[AniListShow] = []
    for show in shows:
        if show.id_mal is None:
            continue
        cached = cache.get(show.id)
        if cached is None or _is_stale(cached["fetched_at"], ttl_days, now):
            to_fetch.append(show)

    if to_fetch:
        logger.info(f"Jikan: fetching MAL ratings for {len(to_fetch)} shows...")
        async with JikanClient() as client:
            for i, show in enumerate(to_fetch):
                mal_id = show.id_mal
                assert mal_id is not None  # to_fetch only holds shows with a MAL id
                payload = await client.get_anime(mal_id)
                if payload is not None:
                    db.upsert_external_rating(
                        source=SOURCE,
                        anilist_id=show.id,
                        payload=payload,
                        mal_id=mal_id,
                        fetched_at=now.format_common_iso(),
                    )
                    cache[show.id] = {
                        "mal_id": mal_id,
                        "payload": payload,
                        "fetched_at": now.format_common_iso(),
                    }
                if i < len(to_fetch) - 1:
                    await asyncio.sleep(client.rate_limit)
    else:
        logger.info("Jikan: all MAL ratings are cached and fresh")

    return {aid: entry["payload"] for aid, entry in cache.items()}
