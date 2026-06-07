"""Tests for the Jikan MAL client and its DB cache integration.

Async coroutines are driven with ``asyncio.run`` to avoid a pytest-asyncio
dependency (the suite has no other async tests).
"""

import asyncio

import httpx
from whenever import Instant

from nyaastats.database import Database
from nyaastats.etl.anilist_client import AniListShow
from nyaastats.etl.jikan_client import JikanClient, fetch_mal_ratings


def _show(anilist_id: int, mal_id: int | None) -> AniListShow:
    return AniListShow(
        id=anilist_id,
        title_romaji="t",
        title_english="t",
        synonyms=[],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color=None,
        start_date=None,
        format="TV",
        id_mal=mal_id,
    )


def _mock_transport(handler):
    return httpx.MockTransport(handler)


async def _run_get_anime(handler, mal_id):
    client = JikanClient()
    client._client = httpx.AsyncClient(transport=_mock_transport(handler))
    try:
        return await client.get_anime(mal_id)
    finally:
        await client._client.aclose()


def test_get_anime_extracts_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/anime/42")
        return httpx.Response(
            200,
            json={
                "data": {
                    "score": 8.5,
                    "scored_by": 1234,
                    "rank": 7,
                    "popularity": 50,
                    "members": 99999,
                    "favorites": 4321,
                    "ignored": "field",
                }
            },
        )

    result = asyncio.run(_run_get_anime(handler, 42))
    assert result == {
        "score": 8.5,
        "scored_by": 1234,
        "rank": 7,
        "popularity": 50,
        "members": 99999,
        "favorites": 4321,
    }


def test_get_anime_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"status": 404})

    result = asyncio.run(_run_get_anime(handler, 999))
    assert result is None


def test_fetch_mal_ratings_uses_and_populates_cache(monkeypatch):
    fixed = Instant.from_utc(2026, 1, 1, 12, 0, 0)
    db = Database(":memory:", now_func=lambda: fixed)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": {"score": 8.0, "scored_by": 10}})

    async def fake_aenter(self):
        self._client = httpx.AsyncClient(transport=_mock_transport(handler))
        return self

    async def _noop_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(JikanClient, "__aenter__", fake_aenter)
    monkeypatch.setattr("nyaastats.etl.jikan_client.asyncio.sleep", _noop_sleep)

    shows = [_show(1, 42), _show(2, None)]  # show 2 has no MAL id, skipped

    ratings = asyncio.run(fetch_mal_ratings(db, shows, now_func=lambda: fixed))
    assert calls["n"] == 1  # only show 1 fetched
    assert ratings[1]["score"] == 8.0
    assert 2 not in ratings

    # Second run should hit cache (no new HTTP calls).
    ratings2 = asyncio.run(fetch_mal_ratings(db, shows, now_func=lambda: fixed))
    assert calls["n"] == 1
    assert ratings2[1]["score"] == 8.0


def test_fetch_mal_ratings_refetches_when_stale(monkeypatch):
    t0 = Instant.from_utc(2026, 1, 1, 12, 0, 0)
    db = Database(":memory:", now_func=lambda: t0)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": {"score": 8.0}})

    async def fake_aenter(self):
        self._client = httpx.AsyncClient(transport=_mock_transport(handler))
        return self

    async def _noop_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(JikanClient, "__aenter__", fake_aenter)
    monkeypatch.setattr("nyaastats.etl.jikan_client.asyncio.sleep", _noop_sleep)

    shows = [_show(1, 42)]
    asyncio.run(fetch_mal_ratings(db, shows, ttl_days=7, now_func=lambda: t0))
    assert calls["n"] == 1

    # 10 days later, with a 7-day TTL, the cached row is stale -> refetch.
    t1 = Instant.from_utc(2026, 1, 11, 12, 0, 0)
    asyncio.run(fetch_mal_ratings(db, shows, ttl_days=7, now_func=lambda: t1))
    assert calls["n"] == 2
