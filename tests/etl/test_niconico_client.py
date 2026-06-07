"""Tests for the Niconico survey CSV ingestion."""

import asyncio

import httpx
from whenever import Instant

from nyaastats.database import Database
from nyaastats.etl.anilist_client import AniListShow
from nyaastats.etl.niconico_client import (
    _normalize_jp,
    _weighted_mean,
    fetch_survey_csv,
    match_surveys_to_shows,
    parse_survey_rows,
)

# A tiny CSV mirroring the real export's columns and Japanese headers.
_CSV = (
    "放送日時,lvID,種別,シーズン,タイトル,話,1,2,3,4,5,エピソード種別,備考\n"
    '"2026-04-06 23:00",1,通常,2026B,テスト作品,1,80.0,10.0,5.0,3.0,2.0,初回,\n'
    '"2026-04-13 23:00",2,通常,2026B,テスト作品,2,60.0,20.0,10.0,5.0,5.0,,\n'
    '"2026-04-20 23:00",3,振り返り,2026B,テスト作品,1,1.0,1.0,1.0,1.0,1.0,,\n'
    '"2026-04-06 22:00",4,通常,2026B,別の 作品！,1,50.0,30.0,10.0,5.0,5.0,,\n'
    '"2026-04-27 23:00",5,通常,2026B,マラソン,1〜12,1.0,1.0,1.0,1.0,1.0,,\n'
    '"2025-10-06 23:00",6,通常,2025D,テスト作品,1,90.0,5.0,3.0,1.0,1.0,,\n'
)


def _show(anilist_id: int, native: str, romaji: str = "r") -> AniListShow:
    return AniListShow(
        id=anilist_id,
        title_romaji=romaji,
        title_english=None,
        synonyms=[],
        episodes=12,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color=None,
        start_date=None,
        format="TV",
        title_native=native,
    )


def test_normalize_strips_width_and_symbols():
    # Full-width and a trailing symbol/space normalize to the same key.
    assert _normalize_jp("別の　作品！") == _normalize_jp("別の作品")
    assert _normalize_jp("4th Season") == _normalize_jp("4th　season")


def test_weighted_mean_best_is_high():
    # All "very good" -> 5.0; all "not good" -> 1.0.
    assert _weighted_mean([100.0, 0, 0, 0, 0]) == 5.0
    assert _weighted_mean([0, 0, 0, 0, 100.0]) == 1.0
    assert _weighted_mean([None, None, None, None, None]) is None


def test_parse_filters_marathons_and_retrospectives():
    rows = parse_survey_rows(_CSV)
    # Excludes the 振り返り row, the marathon range "1〜12"; keeps integer regulars.
    assert all(r["episode"] for r in rows)
    titles_eps = {(r["title"], r["episode"], r["season_code"]) for r in rows}
    assert ("テスト作品", 1, "2026B") in titles_eps
    assert ("テスト作品", 2, "2026B") in titles_eps
    assert ("別の 作品！", 1, "2026B") in titles_eps
    assert ("テスト作品", 1, "2025D") in titles_eps
    # marathon ("1〜12") dropped
    assert not any(r["title"] == "マラソン" for r in rows)
    # retrospective for ep1 dropped, so only the 通常 ep1 (80.0) survives
    ep1 = next(r for r in rows if r["title"] == "テスト作品" and r["episode"] == 1)
    assert ep1["pcts"][0] == 80.0


def test_match_exact_and_fuzzy_and_dedup():
    rows = [r for r in parse_survey_rows(_CSV) if r["season_code"] == "2026B"]
    shows = [
        _show(10, "テスト作品"),  # exact native match
        _show(20, "別の作品"),  # fuzzy: source has extra space + ！
    ]
    matched = match_surveys_to_shows(shows, rows, threshold=85)
    by_key = {(m["anilist_id"], m["episode"]): m for m in matched}
    # show 10 gets episodes 1 and 2; show 20 gets episode 1
    assert (10, 1) in by_key and (10, 2) in by_key
    assert (20, 1) in by_key
    assert by_key[(10, 1)]["very_good_pct"] == 80.0
    assert by_key[(10, 1)]["mean_score"] == _weighted_mean([80.0, 10.0, 5.0, 3.0, 2.0])


def test_match_uses_title_map_override():
    rows = [r for r in parse_survey_rows(_CSV) if r["season_code"] == "2026B"]
    # No native match available; override maps the Japanese title to id 99.
    shows = [_show(99, "completely different")]
    matched = match_surveys_to_shows(
        shows, rows, threshold=99, title_map={"テスト作品": 99}
    )
    assert any(m["anilist_id"] == 99 for m in matched)


def test_fetch_survey_csv_caches(monkeypatch):
    fixed = Instant.from_utc(2026, 6, 1, 12, 0, 0)
    db = Database(":memory:", now_func=lambda: fixed)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=_CSV)

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("nyaastats.etl.niconico_client.httpx.AsyncClient", fake_client)

    text = asyncio.run(fetch_survey_csv(db, now_func=lambda: fixed))
    assert text == _CSV
    assert calls["n"] == 1

    # Within TTL -> served from cache, no new HTTP call.
    text2 = asyncio.run(fetch_survey_csv(db, now_func=lambda: fixed))
    assert text2 == _CSV
    assert calls["n"] == 1
