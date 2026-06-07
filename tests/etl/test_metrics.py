"""Tests for external-rating metric assembly and rank-delta computation."""

from nyaastats.etl.anilist_client import AniListShow
from nyaastats.etl.metrics import (
    build_show_metrics,
    compute_rank_deltas,
)


def _show(anilist_id: int, **kwargs) -> AniListShow:
    defaults = {
        "title_romaji": "t",
        "title_english": "t",
        "synonyms": [],
        "episodes": 12,
        "status": "FINISHED",
        "airing_schedule": [],
        "cover_image_url": None,
        "cover_image_color": None,
        "start_date": None,
        "format": "TV",
    }
    defaults.update(kwargs)
    return AniListShow(id=anilist_id, **defaults)


def test_build_show_metrics_merges_all_sources():
    show = _show(1, id_mal=42, average_score=80, mean_score=81, popularity=1000)
    mal = {1: {"score": 8.1, "scored_by": 500, "rank": 5}}
    nico = {1: [{"very_good_pct": 40.0}, {"very_good_pct": 60.0}]}

    metrics = build_show_metrics([show], mal, nico)

    assert metrics[1]["average_score"] == 80
    assert metrics[1]["mal_id"] == 42
    assert metrics[1]["mal_score"] == 8.1
    assert metrics[1]["mal_rank"] == 5
    # rollup is the mean of per-episode very_good_pct
    assert metrics[1]["niconico_very_good_pct"] == 50.0


def test_build_show_metrics_handles_missing_sources():
    show = _show(1, id_mal=None, average_score=None)
    metrics = build_show_metrics([show])
    assert metrics[1]["mal_score"] is None
    assert metrics[1]["niconico_very_good_pct"] is None


def test_niconico_rollup_ignores_none_values():
    show = _show(1)
    nico = {1: [{"very_good_pct": None}, {"very_good_pct": 30.0}]}
    metrics = build_show_metrics([show], {}, nico)
    assert metrics[1]["niconico_very_good_pct"] == 30.0


def test_compute_rank_deltas_sign_semantics():
    # Show A: many downloads but mediocre reception -> negative delta.
    # Show B: few downloads but loved -> positive delta.
    shows = [
        {
            "anilist_id": 1,
            "total_downloads": 100,
            "mal_score": 7.0,
            "average_score": 70,
            "niconico_very_good_pct": 60.0,
        },
        {
            "anilist_id": 2,
            "total_downloads": 10,
            "mal_score": 9.0,
            "average_score": 90,
            "niconico_very_good_pct": 90.0,
        },
    ]
    compute_rank_deltas(shows)
    by_id = {s["anilist_id"]: s for s in shows}
    # A: dl_rank 1, mal_rank 2 -> 1 - 2 = -1 (downloads outrun reception)
    assert by_id[1]["rank_delta_dl_vs_mal"] == -1
    # B: dl_rank 2, mal_rank 1 -> 2 - 1 = +1 (underrated gem)
    assert by_id[2]["rank_delta_dl_vs_mal"] == 1
    assert by_id[1]["rank_delta_dl_vs_anilist"] == -1
    assert by_id[2]["rank_delta_dl_vs_anilist"] == 1
    # Niconico delta follows the same sign convention.
    assert by_id[1]["rank_delta_dl_vs_niconico"] == -1
    assert by_id[2]["rank_delta_dl_vs_niconico"] == 1


def test_compute_rank_deltas_none_when_metric_missing():
    shows = [
        {
            "anilist_id": 1,
            "total_downloads": 100,
            "mal_score": None,
            "average_score": 70,
        },
        {"anilist_id": 2, "total_downloads": 10, "mal_score": 9.0, "average_score": 90},
    ]
    compute_rank_deltas(shows)
    by_id = {s["anilist_id"]: s for s in shows}
    # Show 1 has no mal_score -> delta is None
    assert by_id[1]["rank_delta_dl_vs_mal"] is None
    # Show 2 still has an anilist delta
    assert by_id[2]["rank_delta_dl_vs_anilist"] is not None
