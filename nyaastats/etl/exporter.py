"""Export aggregated data to JSON formats."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from .anilist_client import AniListShow
from .fuzzy_matcher import TitleMatch

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
        weeks = [week for week in weeks if week_start_date(week) != current_week_sunday]

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

    def export_torrent_diagnostics(
        self,
        torrents_df: pl.DataFrame,
        deltas_df: pl.DataFrame,
        matched_dict: dict[str, TitleMatch],
        shows: list[AniListShow],
        weekly_rankings: pl.DataFrame,
        filename: str = "torrent_downloads_report.json",
    ):
        """Export per-torrent weekly download diagnostics.

        Shows which individual torrents contributed downloads for each
        show+week combination, useful for identifying mismatches or spikes.

        Args:
            torrents_df: DataFrame with infohash, anilist_id, episode, filename
            deltas_df: DataFrame with infohash, timestamp, downloads_delta
            matched_dict: infohash → TitleMatch for match method/score
            shows: AniList show list for title lookup
            weekly_rankings: Weekly rankings to determine top-30 shows
            filename: Output filename
        """
        output_path = self.output_dir / filename

        # Build show title lookup
        title_lookup = {s.id: (s.title_romaji or s.title_english or "") for s in shows}

        # Compute EST Sun-Sat weekly buckets on deltas (same logic as aggregator)
        # Cast timestamp to datetime if stored as string
        deltas_with_ts = deltas_df.with_columns(
            pl.col("timestamp").cast(pl.Datetime("us")).alias("timestamp")
            if deltas_df["timestamp"].dtype == pl.Utf8
            else pl.col("timestamp")
        )
        deltas_with_week = deltas_with_ts.with_columns(
            (pl.col("timestamp") - pl.duration(hours=5)).dt.date().alias("est_date")
        ).with_columns(
            (pl.col("est_date") - pl.duration(days=pl.col("est_date").dt.weekday() % 7))
            .cast(pl.Date)
            .dt.strftime("%Y-%m-%d")
            .alias("week"),
        )

        # Join deltas with torrents to get anilist_id, episode, filename
        torrent_info = torrents_df.select(
            ["infohash", "anilist_id", "episode", "filename"]
        )
        joined = deltas_with_week.join(torrent_info, on="infohash", how="inner")

        # Exclude current in-progress week
        now_est = datetime.now(UTC) - timedelta(hours=5)
        today_est = now_est.date()
        days_since_sunday = (today_est.weekday() + 1) % 7
        current_week_sunday = today_est - timedelta(days=days_since_sunday)
        current_week_str = current_week_sunday.strftime("%Y-%m-%d")
        joined = joined.filter(pl.col("week") != current_week_str)

        # Group by (anilist_id, week, infohash) and sum downloads
        per_torrent = (
            joined.group_by(["anilist_id", "week", "infohash", "episode", "filename"])
            .agg(pl.col("downloads_delta").sum().alias("downloads"))
            .sort(["anilist_id", "week", "downloads"], descending=[False, False, True])
        )

        # Determine which shows to include:
        # 1) Any show in top 30 of any week
        # 2) Any show with >100% week-over-week increase
        top30_ids = set()
        if weekly_rankings is not None and len(weekly_rankings) > 0:
            top30 = weekly_rankings.filter(pl.col("rank") <= 30)
            top30_ids = set(top30["anilist_id"].unique().to_list())

        # Compute per-show per-week totals for WoW change detection
        show_week_totals = (
            per_torrent.group_by(["anilist_id", "week"])
            .agg(pl.col("downloads").sum().alias("total"))
            .sort(["anilist_id", "week"])
        )

        # Find shows with >100% WoW increase
        wow_ids = set()
        for aid in show_week_totals["anilist_id"].unique().to_list():
            show_weeks = show_week_totals.filter(pl.col("anilist_id") == aid).sort(
                "week"
            )
            totals = show_weeks["total"].to_list()
            for i in range(1, len(totals)):
                if totals[i - 1] > 0 and totals[i] / totals[i - 1] > 2.0:
                    wow_ids.add(aid)
                    break

        include_ids = top30_ids | wow_ids

        if not include_ids:
            logger.info("No shows qualify for torrent diagnostics report")
            return

        filtered = per_torrent.filter(pl.col("anilist_id").is_in(include_ids))

        # Build output structure
        shows_output = []
        for aid in sorted(include_ids):
            show_data = filtered.filter(pl.col("anilist_id") == aid)
            if len(show_data) == 0:
                continue

            weeks_list = []
            for week in sorted(show_data["week"].unique().to_list()):
                week_data = show_data.filter(pl.col("week") == week)
                total = int(week_data["downloads"].sum())

                torrents_list = []
                for row in week_data.iter_rows(named=True):
                    infohash = row["infohash"]
                    match = matched_dict.get(infohash)
                    torrents_list.append(
                        {
                            "infohash": infohash,
                            "filename": row["filename"],
                            "episode": row["episode"],
                            "match_method": match.method if match else None,
                            "match_score": match.score if match else None,
                            "downloads": int(row["downloads"]),
                        }
                    )

                weeks_list.append(
                    {
                        "week": week,
                        "total_downloads": total,
                        "torrents": torrents_list,
                    }
                )

            shows_output.append(
                {
                    "anilist_id": aid,
                    "title": title_lookup.get(aid, "Unknown"),
                    "weeks": weeks_list,
                }
            )

        report = {
            "generated": datetime.now(UTC).isoformat(),
            "shows": shows_output,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        file_size = output_path.stat().st_size / 1024
        logger.info(
            f"Exported torrent diagnostics for {len(shows_output)} shows "
            f"to {output_path} ({file_size:.1f} KB)"
        )
