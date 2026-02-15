"""Export movie download data to JSON."""

import json
import logging
from pathlib import Path

import polars as pl

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
