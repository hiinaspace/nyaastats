"""Export seasonal aggregated data for interactive visualizations."""

import json
import logging
from datetime import date, datetime
from pathlib import Path

import polars as pl

from .config import SeasonConfig

logger = logging.getLogger(__name__)


def iso_week_to_monday(week_str: str) -> date:
    """Convert ISO week string (2025-W40) to Monday of that week.

    Args:
        week_str: ISO week string like "2025-W40"

    Returns:
        Date of the Monday of that ISO week
    """
    # Parse "2025-W40" format
    year, week = week_str.split("-W")
    # ISO week 1 is the week containing the first Thursday of the year
    # Use datetime.strptime with ISO week format
    return datetime.strptime(f"{year}-W{week}-1", "%G-W%V-%u").date()


def week_overlaps_range(week_str: str, start_date: date, end_date: date) -> bool:
    """Check if an ISO week overlaps with a date range.

    A week overlaps if any of its days fall within the range.

    Args:
        week_str: ISO week string like "2025-W40"
        start_date: Start of date range (inclusive)
        end_date: End of date range (inclusive)

    Returns:
        True if the week has any overlap with the date range
    """
    from datetime import timedelta

    monday = iso_week_to_monday(week_str)
    sunday = monday + timedelta(days=6)

    # Week overlaps if it starts before range ends AND ends after range starts
    return monday <= end_date and sunday >= start_date


def compute_percentiles(
    data: list[dict], groupby_col: str, value_col: str
) -> dict[str, list[float]]:
    """Compute percentiles across groups.

    Args:
        data: List of dicts with the data
        groupby_col: Column to group by (e.g., "week", "episode")
        value_col: Column to compute percentiles on

    Returns:
        Dict with p25, p50, p75 lists for each group
    """
    df = pl.DataFrame(data)

    if len(df) == 0:
        return {"p25": [], "p50": [], "p75": []}

    # Group and compute percentiles
    percentiles = (
        df.group_by(groupby_col)
        .agg(
            [
                pl.col(value_col).quantile(0.25).alias("p25"),
                pl.col(value_col).quantile(0.50).alias("p50"),
                pl.col(value_col).quantile(0.75).alias("p75"),
            ]
        )
        .sort(groupby_col)
    )

    return {
        "p25": percentiles["p25"].to_list(),
        "p50": percentiles["p50"].to_list(),
        "p75": percentiles["p75"].to_list(),
    }


class SeasonalExporter:
    """Exports seasonal data for interactive visualizations."""

    def __init__(self, output_dir: str | Path):
        """Initialize exporter.

        Args:
            output_dir: Directory to write output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_season_summary(
        self,
        season_config: SeasonConfig,
        weekly_rankings: pl.DataFrame,
        episode_stats: pl.DataFrame,
        season_show_ids: list[int],
    ) -> str:
        """Export seasonal summary JSON with all data needed for visualizations.

        Args:
            season_config: Season configuration (date range, name)
            weekly_rankings: Weekly ranking data
            episode_stats: Episode-level statistics
            season_show_ids: List of AniList IDs for shows in this season

        Returns:
            Path to the generated JSON file
        """
        season_slug = season_config.name.lower().replace(" ", "-")
        filename = f"season-{season_slug}.json"
        output_path = self.output_dir / filename

        # Filter data to season date range
        start_date = season_config.start_date.py_datetime().date()
        end_date = season_config.end_date.py_datetime().date()

        # Filter weekly rankings to season weeks AND season shows only
        filtered_rankings = weekly_rankings.filter(
            pl.col("week").map_elements(
                lambda w: week_overlaps_range(w, start_date, end_date),
                return_dtype=pl.Boolean,
            )
            & pl.col("anilist_id").is_in(season_show_ids)
        )

        if len(filtered_rankings) == 0:
            logger.warning(f"No rankings found for season {season_config.name}")
            return str(output_path)

        # Get unique weeks sorted
        weeks = sorted(filtered_rankings["week"].unique().to_list())

        # Build cumulative downloads per show per week
        show_cumulative: dict[int, int] = {}

        weeks_data = []
        all_weekly_downloads = []  # For percentile computation

        for week in weeks:
            week_data = filtered_rankings.filter(pl.col("week") == week)
            week_start = iso_week_to_monday(week).isoformat()

            rankings_list = []
            for row in week_data.iter_rows(named=True):
                anilist_id = row["anilist_id"]
                downloads = row["downloads"]

                # Update cumulative
                show_cumulative[anilist_id] = (
                    show_cumulative.get(anilist_id, 0) + downloads
                )

                rankings_list.append(
                    {
                        "anilist_id": anilist_id,
                        "rank": row["rank"],
                        "downloads": downloads,
                        "downloads_cumulative": show_cumulative[anilist_id],
                        "title": row["title"],
                        "title_romaji": row["title_romaji"],
                        "cover_image_url": row["cover_image_url"],
                        "cover_image_color": row["cover_image_color"],
                    }
                )

                all_weekly_downloads.append(
                    {
                        "week": week,
                        "downloads": downloads,
                    }
                )

            # Sort by rank
            rankings_list.sort(key=lambda x: x["rank"])

            weeks_data.append(
                {
                    "week": week,
                    "start_date": week_start,
                    "rankings": rankings_list,
                }
            )

        # Build shows summary
        show_ids = filtered_rankings["anilist_id"].unique().to_list()

        # Filter episode stats to season shows (no date cutoff; trust AniList season)
        season_episodes = episode_stats.filter(
            pl.col("anilist_id").is_in(show_ids)
        )

        # Recompute cumulative downloads within the season window
        if len(season_episodes) > 0:
            season_episodes = season_episodes.with_columns(
                pl.col("downloads_daily")
                .cum_sum()
                .over(["anilist_id", "episode"])
                .alias("downloads_cumulative_season")
            )

        shows_data = []
        all_episode_downloads = []  # For percentile computation

        for anilist_id in show_ids:
            # Get show metadata from latest ranking entry
            show_ranking = (
                filtered_rankings.filter(pl.col("anilist_id") == anilist_id)
                .sort("week", descending=True)
                .head(1)
            )

            if len(show_ranking) == 0:
                continue

            show_row = show_ranking.row(0, named=True)

            # Get episode data for this show
            show_episodes = season_episodes.filter(pl.col("anilist_id") == anilist_id)

            # Calculate total downloads (cumulative for season)
            total_downloads = show_cumulative.get(anilist_id, 0)

            # Get episode count and metrics
            episodes_aired = 0
            ep1_downloads = 0
            endurance = None
            latecomers = None

            if len(show_episodes) > 0:
                # Get unique episodes
                unique_episodes = show_episodes["episode"].unique().sort().to_list()
                episodes_aired = len(unique_episodes)
                min_episode = unique_episodes[0] if episodes_aired > 0 else None

                # Per-episode totals and coverage
                per_episode = (
                    show_episodes.group_by("episode")
                    .agg(
                        [
                            pl.col("downloads_daily").sum().alias("downloads_total"),
                            pl.col("days_since_first_torrent")
                            .max()
                            .alias("max_days"),
                        ]
                    )
                    .with_columns(
                        (pl.col("episode") - min_episode + 1).alias("episode_ordinal")
                    )
                )

                # Episode 1 totals
                ep1_data = per_episode.filter(pl.col("episode_ordinal") == 1)
                if len(ep1_data) > 0:
                    ep1_downloads = ep1_data["downloads_total"][0]

                    # Latecomers: share of Ep1 downloads after day 7
                    ep1_stats = show_episodes.filter(pl.col("episode") == min_episode)
                    if len(ep1_stats) > 0:
                        ep1_total = ep1_stats["downloads_daily"].sum()
                        ep1_early = ep1_stats.filter(
                            pl.col("days_since_first_torrent") <= 7
                        )["downloads_daily"].sum()
                        if ep1_total > 0:
                            latecomers = (ep1_total - ep1_early) / ep1_total

                # Endurance: avg of later episodes vs Ep1
                eligible_later = per_episode.filter(
                    (pl.col("episode_ordinal") >= 2)
                    & (pl.col("episode_ordinal") <= 14)
                    & (pl.col("max_days") >= 7)
                )
                if len(eligible_later) > 0 and ep1_downloads > 0:
                    avg_later = eligible_later["downloads_total"].mean()
                    endurance = avg_later / ep1_downloads

                # Collect episode downloads for percentiles
                for ep in unique_episodes:
                    ep_data = show_episodes.filter(pl.col("episode") == ep)
                    if len(ep_data) > 0:
                        all_episode_downloads.append(
                            {
                                "episode": ep,
                                "downloads": ep_data[
                                    "downloads_cumulative_season"
                                ].max(),
                            }
                        )

            # Get current rank (latest week's rank)
            current_rank = show_row["rank"]

            shows_data.append(
                {
                    "anilist_id": anilist_id,
                    "title": show_row["title"],
                    "title_romaji": show_row["title_romaji"],
                    "cover_image_url": show_row["cover_image_url"],
                    "cover_image_color": show_row["cover_image_color"],
                    "total_downloads": total_downloads,
                    "episodes_aired": episodes_aired,
                    "endurance": round(endurance, 3) if endurance is not None else None,
                    "latecomers": round(latecomers, 3) if latecomers is not None else None,
                    "ep1_downloads": int(ep1_downloads) if ep1_downloads else 0,
                    "current_rank": current_rank,
                }
            )

        # Sort shows by total downloads
        shows_data.sort(key=lambda x: x["total_downloads"], reverse=True)

        # Compute percentiles
        weekly_percentiles = compute_percentiles(
            all_weekly_downloads, "week", "downloads"
        )
        episode_percentiles = compute_percentiles(
            all_episode_downloads, "episode", "downloads"
        )

        # Build final output
        output_data = {
            "season": season_config.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weeks": weeks_data,
            "shows": shows_data,
            "percentiles": {
                "weekly_downloads": weekly_percentiles,
                "episode_downloads": episode_percentiles,
            },
        }

        # Write to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        file_size = output_path.stat().st_size / 1024
        logger.info(
            f"Exported season summary to {output_path} "
            f"({len(weeks)} weeks, {len(shows_data)} shows, {file_size:.1f} KB)"
        )

        return str(output_path)

    def export_season_episodes(
        self,
        season_config: SeasonConfig,
        episode_stats: pl.DataFrame,
        shows: list[int],
    ) -> str:
        """Export filtered episode data for season shows.

        Args:
            season_config: Season configuration
            episode_stats: Episode-level statistics
            shows: List of anilist_ids for this season

        Returns:
            Path to the generated JSON file
        """
        season_slug = season_config.name.lower().replace(" ", "-")
        filename = f"episodes-{season_slug}.json"
        output_path = self.output_dir / filename

        # Get season date range
        start_date = season_config.start_date.py_datetime().date()
        end_date = season_config.end_date.py_datetime().date()

        # Filter to season shows AND season date range
        season_episodes = episode_stats.filter(
            pl.col("anilist_id").is_in(shows)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        )

        # Compute season-specific cumulative downloads per episode
        # Sum daily downloads within the season for each episode
        episode_finals = (
            season_episodes.group_by(["anilist_id", "episode"])
            .agg(
                [
                    pl.col("downloads_daily").sum().alias("downloads_cumulative"),
                ]
            )
            .sort(["anilist_id", "episode"])
        )

        # Convert to list of dicts
        episodes_data = [
            {
                "anilist_id": row["anilist_id"],
                "episode": row["episode"],
                "downloads_cumulative": int(row["downloads_cumulative"]),
            }
            for row in episode_finals.iter_rows(named=True)
        ]

        # Write to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(episodes_data, f, indent=2, ensure_ascii=False)

        file_size = output_path.stat().st_size / 1024
        logger.info(
            f"Exported season episodes to {output_path} "
            f"({len(episodes_data)} episode records, {file_size:.1f} KB)"
        )

        return str(output_path)
