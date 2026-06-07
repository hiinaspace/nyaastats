"""Combine external rating signals and compute comparative rank metrics.

``build_show_metrics`` merges AniList scores, MyAnimeList (Jikan) ratings, and
Niconico survey rollups into a single per-show lookup keyed by anilist_id.

``compute_rank_deltas`` operates on a season's list of show dicts and annotates
each with rank-delta metrics that surface shows performing unusually well/poorly
on downloads relative to critical reception.
"""

import logging
from typing import Any

from .anilist_client import AniListShow

logger = logging.getLogger(__name__)


def _niconico_rollup(surveys: list[dict[str, Any]]) -> float | None:
    """Mean of per-episode『とても良かった』% across a show's episodes."""
    vals = [s["very_good_pct"] for s in surveys if s.get("very_good_pct") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _niconico_episode_series(
    surveys: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Compact, episode-sorted『とても良かった』% series for per-show sparklines."""
    series = [
        {"episode": s["episode"], "very_good_pct": s["very_good_pct"]}
        for s in surveys
        if s.get("very_good_pct") is not None and s.get("episode") is not None
    ]
    if not series:
        return None
    series.sort(key=lambda r: r["episode"])
    return series


def build_show_metrics(
    shows: list[AniListShow],
    mal_ratings: dict[int, dict[str, Any]] | None = None,
    niconico_surveys: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[int, dict[str, Any]]:
    """Build a per-show metric lookup keyed by anilist_id.

    Args:
        shows: AniList shows (carry AniList scores + idMal)
        mal_ratings: anilist_id -> Jikan payload (score, scored_by, rank, ...)
        niconico_surveys: anilist_id -> list of per-episode survey dicts

    Returns:
        anilist_id -> dict of metric fields (missing sources left as None).
    """
    mal_ratings = mal_ratings or {}
    niconico_surveys = niconico_surveys or {}

    metrics: dict[int, dict[str, Any]] = {}
    for show in shows:
        mal = mal_ratings.get(show.id) or {}
        nico = niconico_surveys.get(show.id) or []
        metrics[show.id] = {
            "average_score": show.average_score,
            "mean_score": show.mean_score,
            "popularity": show.popularity,
            "favourites": show.favourites,
            "mal_id": show.id_mal,
            "mal_score": mal.get("score"),
            "mal_scored_by": mal.get("scored_by"),
            "mal_rank": mal.get("rank"),
            "niconico_very_good_pct": _niconico_rollup(nico),
            "niconico_episodes": _niconico_episode_series(nico),
        }
    return metrics


def _dense_rank(
    rows: list[dict[str, Any]], key: str, descending: bool = True
) -> dict[int, int]:
    """Rank rows (by anilist_id) on a numeric field, skipping missing values.

    Returns a dict mapping anilist_id -> 1-based rank among rows that have a
    non-null value for ``key``. Rows missing the value are omitted.
    """
    valued = [r for r in rows if r.get(key) is not None]
    valued.sort(key=lambda r: r[key], reverse=descending)
    return {r["anilist_id"]: i + 1 for i, r in enumerate(valued)}


def compute_rank_deltas(shows_data: list[dict[str, Any]]) -> None:
    """Annotate each show dict in-place with rank-delta metrics.

    Ranks shows within this set on downloads, MAL score, AniList average score,
    and Niconico survey approval (rank 1 = best), then stores
    ``rank_delta_dl_vs_mal``, ``rank_delta_dl_vs_anilist`` and
    ``rank_delta_dl_vs_niconico`` as ``download_rank - reception_rank``.

    A *positive* delta means the show ranks better on reception than on downloads
    (a critically loved show with comparatively few downloads — an underrated
    gem). A *negative* delta means downloads outrun reception (popular to
    download but rated lower). Deltas are None when a show lacks one of the
    compared metrics.
    """
    dl_rank = _dense_rank(shows_data, "total_downloads", descending=True)
    mal_rank = _dense_rank(shows_data, "mal_score", descending=True)
    anilist_rank = _dense_rank(shows_data, "average_score", descending=True)
    niconico_rank = _dense_rank(shows_data, "niconico_very_good_pct", descending=True)

    for show in shows_data:
        aid = show["anilist_id"]
        d = dl_rank.get(aid)
        m = mal_rank.get(aid)
        a = anilist_rank.get(aid)
        n = niconico_rank.get(aid)
        show["rank_delta_dl_vs_mal"] = (
            (d - m) if (d is not None and m is not None) else None
        )
        show["rank_delta_dl_vs_anilist"] = (
            (d - a) if (d is not None and a is not None) else None
        )
        show["rank_delta_dl_vs_niconico"] = (
            (d - n) if (d is not None and n is not None) else None
        )
