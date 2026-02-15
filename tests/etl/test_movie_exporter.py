import json

import polars as pl

from nyaastats.etl.anilist_client import AniListShow
from nyaastats.etl.fuzzy_matcher import TitleMatch
from nyaastats.etl.movie_exporter import MovieExporter


def _sample_show(anilist_id: int, title: str) -> AniListShow:
    return AniListShow(
        id=anilist_id,
        title_romaji=title,
        title_english=title,
        synonyms=[],
        episodes=1,
        status="FINISHED",
        airing_schedule=[],
        cover_image_url=None,
        cover_image_color=None,
        start_date=(2025, 10, 1),
        format="MOVIE",
    )


def test_export_movie_match_report_empty(tmp_path):
    exporter = MovieExporter(tmp_path)
    output_path = exporter.export_movie_match_report(
        movie_torrents=pl.DataFrame(
            {
                "infohash": [],
                "filename": [],
                "pubdate": [],
                "guessit_data": [],
                "trusted": [],
                "remake": [],
                "anilist_id": [],
            }
        ),
        movie_shows=[],
        movie_matches={},
    )

    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data == {"movies": []}


def test_export_movie_match_report_populated(tmp_path):
    exporter = MovieExporter(tmp_path)
    show = _sample_show(113971, "Kidou Senshi Gundam: Senkou no Hathaway - Circe no Majo")
    match = TitleMatch(
        anilist_id=113971,
        score=97.0,
        method="manual_override",
        matched_title=show.title_romaji,
        season_matched=None,
    )

    output_path = exporter.export_movie_match_report(
        movie_torrents=pl.DataFrame(
            {
                "infohash": ["abc123"],
                "filename": ["[Group] Movie.mkv"],
                "pubdate": ["2025-10-07T00:00:00Z"],
                "guessit_data": [
                    json.dumps(
                        {"title": "Kidou Senshi Gundam", "season": None, "episode": None}
                    )
                ],
                "trusted": [1],
                "remake": [0],
                "anilist_id": [113971],
            }
        ),
        movie_shows=[show],
        movie_matches={"abc123": match},
    )

    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)

    assert len(data["movies"]) == 1
    movie = data["movies"][0]
    assert movie["anilist_id"] == 113971
    assert movie["torrent_count"] == 1
    torrent = movie["torrents"][0]
    assert torrent["filename"] == "[Group] Movie.mkv"
    assert torrent["guessit_title"] == "Kidou Senshi Gundam"
    assert torrent["match"]["method"] == "manual_override"
    assert torrent["match"]["score"] == 97.0
