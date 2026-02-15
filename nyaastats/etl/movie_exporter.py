"""Export movie download data to JSON."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from .anilist_client import AniListShow
    from .fuzzy_matcher import TitleMatch

logger = logging.getLogger(__name__)


class MovieExporter:
    """Exports movie download data to JSON."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_movies(
        self, movie_stats: pl.DataFrame, filename: str = "movies.json"
    ) -> str:
        """Export movie download stats to JSON.

        Args:
            movie_stats: DataFrame from MovieAggregator.aggregate_movie_downloads
            filename: Output filename

        Returns:
            Path to the generated JSON file
        """
        output_path = self.output_dir / filename

        if len(movie_stats) == 0:
            logger.warning("No movie data to export")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"movies": []}, f, indent=2)
            return str(output_path)

        # Get unique movies
        movie_ids = movie_stats["anilist_id"].unique().to_list()

        movies_data = []
        for anilist_id in movie_ids:
            movie_rows = movie_stats.filter(pl.col("anilist_id") == anilist_id).sort(
                "weeks_since_release"
            )

            if len(movie_rows) == 0:
                continue

            first_row = movie_rows.row(0, named=True)
            last_row = movie_rows.row(-1, named=True)

            # Build weekly downloads array
            weekly_downloads = [
                {
                    "weeks_since_release": int(row["weeks_since_release"]),
                    "week_start": row["week_start"].isoformat()
                    if row["week_start"]
                    else None,
                    "downloads_weekly": int(row["downloads_weekly"]),
                    "downloads_cumulative": int(row["downloads_cumulative"]),
                }
                for row in movie_rows.iter_rows(named=True)
            ]

            # Format first torrent date
            first_dt = first_row.get("first_datetime")
            first_torrent_date = first_dt.strftime("%Y-%m-%d") if first_dt else None

            movies_data.append(
                {
                    "anilist_id": anilist_id,
                    "title": first_row["title_english"],
                    "title_romaji": first_row["title"],
                    "cover_image_url": first_row["cover_image_url"],
                    "cover_image_color": first_row["cover_image_color"],
                    "total_downloads": int(last_row["downloads_cumulative"]),
                    "first_torrent_date": first_torrent_date,
                    "weekly_downloads": weekly_downloads,
                }
            )

        # Sort by total downloads descending
        movies_data.sort(key=lambda m: m["total_downloads"], reverse=True)

        output = {"movies": movies_data}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        file_size = output_path.stat().st_size / 1024
        logger.info(
            f"Exported {len(movies_data)} movies to {output_path} ({file_size:.1f} KB)"
        )

        return str(output_path)

    def export_movie_match_report(
        self,
        movie_torrents: pl.DataFrame,
        movie_shows: list["AniListShow"],
        movie_matches: dict[str, "TitleMatch"],
        filename: str = "movie_match_report.json",
    ) -> str:
        """Export per-movie matched torrent filenames and guessit output.

        Args:
            movie_torrents: Matched movie torrents dataframe from MovieAggregator
            movie_shows: AniList movie metadata used for matching
            movie_matches: Dict mapping infohash -> TitleMatch
            filename: Output filename

        Returns:
            Path to the generated JSON file
        """
        output_path = self.output_dir / filename

        if len(movie_torrents) == 0:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"movies": []}, f, indent=2)
            logger.info(f"Exported empty movie match report to {output_path}")
            return str(output_path)

        show_lookup = {show.id: show for show in movie_shows}
        movie_rows: dict[int, list[dict]] = {}

        for row in movie_torrents.iter_rows(named=True):
            anilist_id = row["anilist_id"]
            infohash = row["infohash"]
            raw_guessit = row.get("guessit_data")
            guessit = {}
            if isinstance(raw_guessit, str):
                try:
                    guessit = json.loads(raw_guessit)
                except json.JSONDecodeError:
                    guessit = {"_parse_error": "invalid_json", "_raw": raw_guessit}

            match = movie_matches.get(infohash)
            torrent_entry = {
                "infohash": infohash,
                "filename": row.get("filename"),
                "pubdate": row.get("pubdate"),
                "trusted": bool(row.get("trusted")),
                "remake": bool(row.get("remake")),
                "guessit": guessit,
                "guessit_title": guessit.get("title"),
                "guessit_season": guessit.get("season"),
                "guessit_episode": guessit.get("episode"),
                "match": {
                    "method": match.method if match else None,
                    "score": match.score if match else None,
                    "matched_title": match.matched_title if match else None,
                    "season_matched": match.season_matched if match else None,
                },
            }
            movie_rows.setdefault(anilist_id, []).append(torrent_entry)

        movies_data = []
        for anilist_id in sorted(movie_rows.keys()):
            show = show_lookup.get(anilist_id)
            title_romaji = show.title_romaji if show else "Unknown"
            title_english = (
                show.title_english if show and show.title_english else title_romaji
            )
            torrents = sorted(
                movie_rows[anilist_id],
                key=lambda t: (t["pubdate"] or "", t["filename"] or ""),
            )

            movies_data.append(
                {
                    "anilist_id": anilist_id,
                    "title": title_english,
                    "title_romaji": title_romaji,
                    "torrent_count": len(torrents),
                    "torrents": torrents,
                }
            )

        movies_data.sort(key=lambda m: m["torrent_count"], reverse=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"movies": movies_data}, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Exported movie match report to {output_path} ({len(movies_data)} movies)"
        )
        return str(output_path)
