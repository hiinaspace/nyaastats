"""Export aggregated data to Parquet and JSON formats."""

import json
import logging
from pathlib import Path
from datetime import date, datetime

import polars as pl

logger = logging.getLogger(__name__)


def iso_week_to_monday(week_str: str) -> date:
    """Convert ISO week string (2025-W40) to Monday of that week."""
    year, week = week_str.split("-W")
    return datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()


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
        """Export episode stats to Parquet.

        Args:
            daily_stats: DataFrame with episode statistics (hourly for first 7 days)
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Select and order columns for output
        # Sort by days_since_first_torrent since data is aligned to first torrent
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
        ).sort(["anilist_id", "episode", "days_since_first_torrent"])

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
                [
                    "anilist_id",
                    "rank",
                    "downloads",
                    "title",
                    "title_romaji",
                    "cover_image_url",
                    "cover_image_color",
                ]
            ).to_dicts()

            # Get week start date (Monday of ISO week)
            week_start = iso_week_to_monday(week).isoformat()
            week_entry = {
                "week": week,
                "start_date": week_start,
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

    def export_shows_metadata(
        self,
        seasons_data: dict[str, list],
        weekly_rankings: pl.DataFrame,
        filename: str = "shows.json",
    ):
        """Export show metadata grouped by season for sidebar navigation.

        Args:
            seasons_data: Dict mapping season name to list of AniListShow objects
            weekly_rankings: DataFrame with weekly rankings (for current rank)
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Get the most recent week's rankings for current rank
        latest_week = weekly_rankings["week"].max()
        latest_rankings = weekly_rankings.filter(pl.col("week") == latest_week)

        # Build rank lookup: anilist_id -> rank
        rank_lookup = {
            row["anilist_id"]: row["rank"]
            for row in latest_rankings.iter_rows(named=True)
        }

        shows_by_season = {}

        for season_name, shows in seasons_data.items():
            season_shows = []
            for show in shows:
                # Only include shows that have rankings (i.e., have download data)
                if show.id not in rank_lookup:
                    continue

                season_shows.append(
                    {
                        "id": show.id,
                        "title": show.title_english or show.title_romaji,
                        "title_romaji": show.title_romaji,
                        "rank": rank_lookup.get(show.id),
                        "cover_image_url": show.cover_image_url,
                        "cover_image_color": show.cover_image_color,
                    }
                )

            # Sort by rank
            season_shows.sort(key=lambda x: x["rank"] if x["rank"] else 999)
            shows_by_season[season_name] = season_shows

        # Write to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(shows_by_season, f, indent=2, ensure_ascii=False)

        total_shows = sum(len(shows) for shows in shows_by_season.values())
        file_size = output_path.stat().st_size / 1024  # KB
        logger.info(
            f"Exported {total_shows} shows across {len(shows_by_season)} seasons "
            f"to {output_path} ({file_size:.1f} KB)"
        )
