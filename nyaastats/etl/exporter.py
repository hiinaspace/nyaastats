"""Export aggregated data to Parquet and JSON formats."""

import json
import logging
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class DataExporter:
    """Exports processed data to Parquet and JSON."""

    def __init__(self, output_dir: str | Path):
        """Initialize exporter.

        Args:
            output_dir: Directory to write output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_episode_stats(
        self, daily_stats: pl.DataFrame, filename: str = "episodes.parquet"
    ):
        """Export daily episode stats to Parquet.

        Args:
            daily_stats: DataFrame with daily episode statistics
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Select and order columns for output
        output_df = daily_stats.select(
            [
                "anilist_id",
                "episode",
                "date",
                "downloads_daily",
                "downloads_cumulative",
                "days_since_first_torrent",
                "title",
                "title_english",
            ]
        ).sort(["anilist_id", "episode", "date"])

        # Write to Parquet
        output_df.write_parquet(output_path, compression="snappy")

        file_size = output_path.stat().st_size / 1024  # KB
        logger.info(
            f"Exported {len(output_df)} episode stats to {output_path} "
            f"({file_size:.1f} KB)"
        )

    def export_weekly_rankings(
        self, weekly_rankings: pl.DataFrame, filename: str = "rankings.json"
    ):
        """Export weekly rankings to JSON.

        Args:
            weekly_rankings: DataFrame with weekly rankings
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Group by week and convert to structured JSON
        weeks = weekly_rankings["week"].unique().sort().to_list()

        rankings_data = {
            "season": "Fall 2025 & Winter 2026",  # TODO: make dynamic
            "weeks": [],
        }

        for week in weeks:
            week_data = weekly_rankings.filter(pl.col("week") == week)

            # Convert to list of dicts
            rankings_list = week_data.select(
                ["anilist_id", "rank", "downloads", "title", "title_romaji"]
            ).to_dicts()

            # Get week start date (Monday of ISO week)
            # For now, just use the week string
            week_entry = {
                "week": week,
                "start_date": None,  # TODO: calculate from ISO week if needed
                "rankings": rankings_list,
            }

            rankings_data["weeks"].append(week_entry)

        # Write to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rankings_data, f, indent=2, ensure_ascii=False)

        file_size = output_path.stat().st_size / 1024  # KB
        logger.info(
            f"Exported {len(weeks)} weeks of rankings to {output_path} "
            f"({file_size:.1f} KB)"
        )

    def write_match_report(
        self,
        matched: list[tuple[str, any]],
        unmatched: list[tuple[str, str, float | None]],
        filename: str = "match_report.txt",
    ):
        """Write diagnostic report of fuzzy matching results.

        Args:
            matched: List of (infohash, TitleMatch) tuples
            unmatched: List of (infohash, title, best_score) tuples
            filename: Output filename
        """
        output_path = self.output_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Fuzzy Matching Report\n")
            f.write("=" * 80 + "\n\n")

            total = len(matched) + len(unmatched)
            success_rate = len(matched) / total * 100 if total > 0 else 0

            f.write(f"Total torrents: {total}\n")
            f.write(f"Matched: {len(matched)} ({success_rate:.1f}%)\n")
            f.write(f"Unmatched: {len(unmatched)}\n\n")

            # Matched samples
            f.write("-" * 80 + "\n")
            f.write("Sample Matched Torrents (first 20):\n")
            f.write("-" * 80 + "\n")
            for infohash, match in matched[:20]:
                f.write(f"AniList ID: {match.anilist_id}\n")
                f.write(f"  Matched Title: {match.matched_title}\n")
                f.write(f"  Method: {match.method}\n")
                f.write(f"  Score: {match.score:.1f}\n")
                f.write(f"  Infohash: {infohash[:16]}...\n\n")

            # Unmatched samples
            if unmatched:
                f.write("-" * 80 + "\n")
                f.write("Sample Unmatched Torrents (first 20):\n")
                f.write("-" * 80 + "\n")
                for infohash, title, best_score in unmatched[:20]:
                    f.write(f"Title: {title}\n")
                    f.write(f"  Best Score: {best_score if best_score else 'N/A'}\n")
                    f.write(f"  Infohash: {infohash[:16]}...\n\n")

        logger.info(f"Wrote match report to {output_path}")
