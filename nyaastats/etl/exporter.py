"""Export aggregated data to JSON formats."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


def week_start_date(week_str: str) -> date:
    """Parse a week identifier (YYYY-MM-DD Sunday start) into a date."""
    return date.fromisoformat(week_str)


class DataExporter:
    """Exports processed data to JSON."""

    def __init__(self, output_dir: str | Path):
        """Initialize exporter.

        Args:
            output_dir: Directory to write output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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
        # Compute the current EST week's Sunday start to exclude in-progress week
        now_est = datetime.now(UTC) - timedelta(hours=5)
        today_est = now_est.date()
        days_since_sunday = (today_est.weekday() + 1) % 7
        current_week_sunday = today_est - timedelta(days=days_since_sunday)
        weeks = [
            week
            for week in weeks
            if week_start_date(week) != current_week_sunday
        ]

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

            week_entry = {
                "week": week,
                "start_date": week,  # week identifier is already the Sunday start date
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
