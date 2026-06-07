"""Ingest Niconico per-episode survey (公式アンケート) ratings.

Source: ``nicolive-anime-survey.info``, a fan-run database of Niconico official
live-broadcast satisfaction surveys that offers a full CSV export of every
catalogued broadcast. Each row is one broadcast of one episode with the 5-point
scale distribution as percentages (column ``1`` = 『とても良かった』"very good" …
column ``5`` = 『良くなかった』"not good").

Pipeline:
  1. Download/cache the CSV (one request for the whole archive).
  2. Keep only regular (通常) broadcasts with a plain integer episode number,
     dropping marathons (一挙) and retrospectives (振り返り) that would double-count.
  3. Match the Japanese title to an AniList show via its native title.
  4. Upsert per-episode rows into the ``niconico_survey`` table.

This source carries survey *ratings* only — Niconico view counts are not part of
it and would require scraping individual live-broadcast pages.
"""

import csv
import io
import logging
import unicodedata
from collections.abc import Callable
from typing import Any

import httpx
from thefuzz import fuzz
from whenever import Instant

from .anilist_client import AniListShow
from .config import (
    NICONICO_CSV_TTL_DAYS,
    NICONICO_MATCH_THRESHOLD,
    NICONICO_SURVEY_CSV_URL,
    NICONICO_TITLE_MAP,
    niconico_season_code,
)

logger = logging.getLogger(__name__)

# Column headers in the exported CSV (Japanese).
_COL_SEASON = "シーズン"
_COL_TITLE = "タイトル"
_COL_EPISODE = "話"
_COL_TYPE = "種別"
_COL_DATETIME = "放送日時"
_REGULAR_BROADCAST = "通常"  # exclude 一挙 (marathon) / 振り返り (retrospective)

# Cache key for the raw CSV inside the external_ratings table.
_CSV_CACHE_SOURCE = "niconico_csv"


def _normalize_jp(title: str) -> str:
    """Normalize a (usually Japanese) title for matching.

    NFKC folds full/half-width variants together; we then strip whitespace and
    a handful of punctuation/symbols that vary between sources, and lowercase any
    latin so e.g. "4th Season" / "4th season" collapse.
    """
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", title)
    text = text.lower()
    # Drop whitespace and common separators/symbols that differ between sources.
    stripped = []
    for ch in text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):  # punctuation / symbols
            continue
        stripped.append(ch)
    return "".join(stripped)


def _parse_pct(value: str | None) -> float | None:
    """Parse a percentage cell; empty/invalid -> None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _weighted_mean(pcts: list[float | None]) -> float | None:
    """Weighted mean on a 1-5 scale where **5 = best** (とても良かった).

    The source orders columns best→worst (1=very good); we invert the weights so
    a higher score is better and intuitive alongside MAL/AniList scores.
    """
    weights = [5, 4, 3, 2, 1]
    total = sum(p for p in pcts if p is not None)
    if total <= 0:
        return None
    acc = sum(w * p for w, p in zip(weights, pcts, strict=False) if p is not None)
    return round(acc / total, 3)


async def fetch_survey_csv(
    db: Any,
    *,
    url: str = NICONICO_SURVEY_CSV_URL,
    ttl_days: int = NICONICO_CSV_TTL_DAYS,
    now_func: Callable[[], Instant] = Instant.now,
) -> str | None:
    """Return the survey CSV text, using a cached copy until it is ``ttl_days`` old.

    The raw CSV is cached in the ``external_ratings`` table (source
    ``niconico_csv``, anilist_id 0) so reruns within the TTL don't re-download.
    """
    now = now_func()
    cached = db.get_external_ratings(_CSV_CACHE_SOURCE).get(0)
    if cached is not None:
        fetched_at = cached.get("fetched_at")
        if fetched_at is not None:
            age = now.timestamp() - Instant.parse_common_iso(fetched_at).timestamp()
            if age < ttl_days * 86400:
                return cached["payload"].get("csv")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except httpx.HTTPError as exc:
        logger.warning("Failed to download Niconico survey CSV: %s", exc)
        if cached is not None:  # fall back to a stale copy rather than nothing
            return cached["payload"].get("csv")
        return None

    db.upsert_external_rating(
        _CSV_CACHE_SOURCE,
        0,
        {"csv": text},
        fetched_at=now.format_common_iso(),
    )
    return text


def parse_survey_rows(csv_text: str) -> list[dict[str, Any]]:
    """Parse the CSV into normalized per-episode survey rows.

    Keeps only regular broadcasts with an integer episode number. Returns dicts
    with ``season_code``, ``title``, ``episode`` and the five percentages.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if raw.get(_COL_TYPE) != _REGULAR_BROADCAST:
            continue
        ep_raw = (raw.get(_COL_EPISODE) or "").strip()
        if not ep_raw.isdigit():
            continue
        title = (raw.get(_COL_TITLE) or "").strip()
        if not title:
            continue
        rows.append(
            {
                "season_code": (raw.get(_COL_SEASON) or "").strip(),
                "title": title,
                "episode": int(ep_raw),
                "datetime": (raw.get(_COL_DATETIME) or "").strip(),
                "pcts": [_parse_pct(raw.get(str(i))) for i in range(1, 6)],
            }
        )
    return rows


def _build_title_index(
    shows: list[AniListShow],
) -> tuple[dict[str, int], list[tuple[str, int]]]:
    """Build lookup structures for matching Niconico titles to shows.

    Returns ``(exact, fuzzy)`` where ``exact`` maps a normalized title variant to
    an anilist id, and ``fuzzy`` is a list of ``(normalized_native, anilist_id)``
    used for fuzzy fallback (native title is the most reliable JP signal).
    """
    exact: dict[str, int] = {}
    fuzzy: list[tuple[str, int]] = []
    for show in shows:
        variants = [show.title_native, show.title_romaji, show.title_english]
        variants.extend(show.synonyms or [])
        for variant in variants:
            norm = _normalize_jp(variant) if variant else ""
            if norm:
                exact.setdefault(norm, show.id)
        native_norm = _normalize_jp(show.title_native) if show.title_native else ""
        if native_norm:
            fuzzy.append((native_norm, show.id))
    return exact, fuzzy


def match_surveys_to_shows(
    shows: list[AniListShow],
    rows: list[dict[str, Any]],
    *,
    threshold: int = NICONICO_MATCH_THRESHOLD,
    title_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Match parsed survey rows to AniList shows.

    Matching order per row: manual ``title_map`` override → exact normalized title
    → best fuzzy match against native titles above ``threshold``. Unmatched rows
    are dropped. Deduplicates to one row per (anilist_id, episode), keeping the
    earliest broadcast.
    """
    title_map = title_map if title_map is not None else NICONICO_TITLE_MAP
    exact, fuzzy = _build_title_index(shows)
    # Resolve manual overrides against the same normalization.
    override = {_normalize_jp(k): v for k, v in title_map.items()}

    matched: dict[tuple[int, int], dict[str, Any]] = {}
    unmatched_titles: set[str] = set()
    for row in sorted(rows, key=lambda r: r["datetime"]):
        norm = _normalize_jp(row["title"])
        anilist_id = override.get(norm) or exact.get(norm)
        if anilist_id is None and fuzzy:
            best_id, best_score = None, 0
            for native_norm, sid in fuzzy:
                score = fuzz.ratio(norm, native_norm)
                # Niconico often uses a shorter title than AniList's native one
                # (which appends cours/arc suffixes like "2年生編 1学期"). A
                # substring (partial) match catches those, length-gated so a short
                # common substring can't spuriously match an unrelated long title.
                if min(len(norm), len(native_norm)) >= 8:
                    score = max(score, fuzz.partial_ratio(norm, native_norm))
                if score > best_score:
                    best_id, best_score = sid, score
            if best_score >= threshold:
                anilist_id = best_id
        if anilist_id is None:
            unmatched_titles.add(row["title"])
            continue

        key = (anilist_id, row["episode"])
        if key in matched:  # keep earliest broadcast (rows sorted ascending)
            continue
        p = row["pcts"]
        matched[key] = {
            "anilist_id": anilist_id,
            "episode": row["episode"],
            "very_good_pct": p[0],
            "good_pct": p[1],
            "normal_pct": p[2],
            "bad_pct": p[3],
            "very_bad_pct": p[4],
            "mean_score": _weighted_mean(p),
        }

    if unmatched_titles:
        logger.info(
            "Niconico: %d titles had survey data but no AniList match (e.g. %s)",
            len(unmatched_titles),
            ", ".join(list(unmatched_titles)[:5]),
        )
    return list(matched.values())


async def ingest_niconico_surveys(
    db: Any,
    shows: list[AniListShow],
    seasons: list[Any],
    *,
    now_func: Callable[[], Instant] = Instant.now,
) -> int:
    """Download, match, and store Niconico surveys for the given seasons.

    Returns the number of per-episode rows upserted. Safe to call on every ETL
    run: the CSV is cached and rows are idempotently upserted.
    """
    csv_text = await fetch_survey_csv(db, now_func=now_func)
    if not csv_text:
        logger.info("Niconico: no survey CSV available, skipping")
        return 0

    season_codes = {
        code
        for s in seasons
        if (code := niconico_season_code(s.season, s.year)) is not None
    }
    rows = [r for r in parse_survey_rows(csv_text) if r["season_code"] in season_codes]
    matched = match_surveys_to_shows(shows, rows)

    fetched_at = now_func().format_common_iso()
    for m in matched:
        db.upsert_niconico_survey(
            m["anilist_id"],
            m["episode"],
            very_good_pct=m["very_good_pct"],
            good_pct=m["good_pct"],
            normal_pct=m["normal_pct"],
            bad_pct=m["bad_pct"],
            very_bad_pct=m["very_bad_pct"],
            mean_score=m["mean_score"],
            source_url=NICONICO_SURVEY_CSV_URL,
            fetched_at=fetched_at,
        )
    shows_covered = len({m["anilist_id"] for m in matched})
    logger.info(
        "Niconico: stored %d episode surveys across %d shows (from %d season rows)",
        len(matched),
        shows_covered,
        len(rows),
    )
    return len(matched)
