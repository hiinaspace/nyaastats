"""Download aggregation and time-series processing."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from .anilist_client import AniListShow
from .config import SeasonConfig
from .fuzzy_matcher import TitleMatch

logger = logging.getLogger(__name__)


@dataclass
class EpisodeStats:
    """Aggregated statistics per episode and date."""

    anilist_id: int
    episode: int
    date: datetime
    downloads_daily: int
    downloads_cumulative: int
    days_since_first_torrent: float


@dataclass
class WeeklyRanking:
    """Weekly ranking for bump chart."""

    week: str  # ISO week "2025-W40"
    anilist_id: int
    rank: int
    downloads: int
    title: str
    title_romaji: str


class DownloadAggregator:
    """Aggregates download stats from raw torrent data."""

    def __init__(self, db_path: str | Path):
        """Initialize aggregator.

        Args:
            db_path: Path to nyaastats SQLite database
        """
        self.db_path = str(db_path)
        # Use Polars for direct SQLite reading instead of DuckDB
        # (DuckDB requires downloading extensions which may not work in all environments)
        import sqlite3
        self.sqlite_conn = sqlite3.connect(self.db_path)

    def load_and_filter_torrents(
        self, seasons: list[SeasonConfig], matched_torrents: dict[str, TitleMatch]
    ) -> pl.DataFrame:
        """Load torrents from database and filter to matched ones.

        Args:
            seasons: List of seasons to include
            matched_torrents: Dict mapping infohash to TitleMatch

        Returns:
            Polars DataFrame with filtered torrents and metadata
        """
        # Build date filter
        min_date = min(s.start_date for s in seasons).format_common_iso()

        # Load torrents with guessit data using Polars SQL connector
        query = f"""
        SELECT
            infohash,
            filename,
            pubdate,
            guessit_data,
            trusted,
            remake
        FROM torrents
        WHERE pubdate >= '{min_date}'
            AND (status IS NULL OR status != 'guessit_failed')
            AND guessit_data IS NOT NULL
        """

        df = pl.read_database(query, connection=self.sqlite_conn)

        logger.info(f"Loaded {len(df)} torrents from database")

        # Parse guessit JSON and add episode/title columns
        import json

        def extract_title(guessit_json: str) -> str | None:
            """Extract title from guessit JSON."""
            try:
                data = json.loads(guessit_json)
                return data.get("title")
            except Exception:
                return None

        def extract_episode(guessit_json: str) -> int | None:
            """Extract episode number from guessit JSON.

            Returns None for batch torrents (episode as list) or invalid data.
            """
            try:
                data = json.loads(guessit_json)
                episode = data.get("episode")

                # Filter out batch torrents (episode as list)
                if isinstance(episode, (list, tuple)):
                    return None
                elif episode is not None:
                    # Convert to int if it's not already
                    try:
                        return int(episode)
                    except (ValueError, TypeError):
                        return None
                return None
            except Exception:
                return None

        # Extract title and episode from guessit JSON
        df = df.with_columns([
            pl.col("guessit_data")
            .map_elements(extract_title, return_dtype=pl.Utf8)
            .alias("title"),
            pl.col("guessit_data")
            .map_elements(extract_episode, return_dtype=pl.Int64)
            .alias("episode"),
        ])

        # Filter out invalid episodes (nulls and batches already handled in parse_guessit)
        df = df.filter(pl.col("episode").is_not_null())

        logger.info(f"After filtering batches: {len(df)} torrents")

        # Filter to matched torrents only
        matched_infohashes = set(matched_torrents.keys())
        df = df.filter(pl.col("infohash").is_in(matched_infohashes))

        logger.info(f"After filtering to matched: {len(df)} torrents")

        # Add anilist_id from matches
        df = df.with_columns(
            pl.col("infohash")
            .map_elements(
                lambda h: matched_torrents[h].anilist_id if h in matched_torrents else None,
                return_dtype=pl.Int64,
            )
            .alias("anilist_id")
        )

        return df

    def calculate_download_deltas(
        self, torrents_df: pl.DataFrame
    ) -> pl.DataFrame:
        """Calculate download deltas from stats time series.

        Uses Polars window functions for efficient computation.

        Args:
            torrents_df: DataFrame of filtered torrents

        Returns:
            DataFrame with (infohash, timestamp, downloads_delta) rows
        """
        infohashes = torrents_df["infohash"].to_list()

        # Load stats for these torrents
        # Build safe IN clause by quoting infohashes (they're hex strings, safe to include)
        infohashes_quoted = ",".join(f"'{h}'" for h in infohashes)
        query = f"""
        SELECT
            infohash,
            timestamp,
            downloads
        FROM stats
        WHERE infohash IN ({infohashes_quoted})
        ORDER BY infohash, timestamp
        """

        stats_df = pl.read_database(query, connection=self.sqlite_conn)

        if len(stats_df) == 0:
            logger.warning("No stats found for any torrents")
            return pl.DataFrame({
                "infohash": [],
                "timestamp": [],
                "downloads_delta": []
            })

        # Calculate deltas using Polars window functions
        stats_df = stats_df.with_columns(
            [
                pl.col("downloads")
                .shift(1)
                .over("infohash")
                .alias("prev_downloads")
            ]
        )

        # Calculate delta
        stats_df = stats_df.with_columns(
            [
                pl.when(pl.col("prev_downloads").is_null())
                .then(0)  # First observation
                .when(pl.col("downloads") > pl.col("prev_downloads"))
                .then(pl.col("downloads") - pl.col("prev_downloads"))
                .otherwise(0)  # Handle any decreases
                .alias("downloads_delta")
            ]
        )

        deltas_df = stats_df.select(["infohash", "timestamp", "downloads_delta"])

        logger.info(f"Calculated deltas for {deltas_df['infohash'].n_unique()} torrents")

        return deltas_df

    def aggregate_by_episode_and_date(
        self,
        torrents_df: pl.DataFrame,
        deltas_df: pl.DataFrame,
        shows: list[AniListShow],
    ) -> pl.DataFrame:
        """Aggregate downloads by (anilist_id, episode, time_bucket).

        Uses hourly resolution for first 7 days, daily resolution after.
        Time is aligned to each episode's first torrent timestamp.

        Args:
            torrents_df: Filtered torrents with metadata
            deltas_df: Download deltas
            shows: List of AniList shows for metadata

        Returns:
            DataFrame with episode stats at variable resolution
        """
        # Join torrents with deltas
        combined = deltas_df.join(
            torrents_df.select(["infohash", "anilist_id", "episode", "pubdate"]),
            on="infohash",
            how="inner",
        )

        # Parse timestamp
        combined = combined.with_columns(
            [
                pl.col("timestamp").str.to_datetime(format="%+", time_zone="UTC").alias("datetime"),
            ]
        )

        # Find the first torrent timestamp per episode
        first_torrent = (
            torrents_df.group_by(["anilist_id", "episode"])
            .agg(pl.col("pubdate").min().alias("first_torrent_timestamp"))
        )

        # Parse first_torrent_timestamp
        first_torrent = first_torrent.with_columns(
            pl.col("first_torrent_timestamp")
            .str.to_datetime(format="%+", time_zone="UTC")
            .alias("first_datetime")
        )

        combined = combined.join(
            first_torrent.select(["anilist_id", "episode", "first_datetime"]),
            on=["anilist_id", "episode"],
            how="left"
        )

        # Calculate hours since first torrent (exact)
        combined = combined.with_columns(
            (
                (pl.col("datetime") - pl.col("first_datetime"))
                .dt.total_seconds()
                / 3600
            ).alias("hours_since_first_torrent")
        )

        # Create time buckets: hourly for first 7 days (168 hours), daily after
        combined = combined.with_columns(
            pl.when(pl.col("hours_since_first_torrent") <= 168)
            .then(pl.col("hours_since_first_torrent").floor())  # hourly bucket
            .otherwise(
                # After 7 days, use 24-hour buckets aligned to first torrent
                168 + ((pl.col("hours_since_first_torrent") - 168) / 24).floor() * 24
            )
            .alias("time_bucket_hours")
        )

        # Aggregate by (anilist_id, episode, time_bucket)
        stats = (
            combined.group_by(["anilist_id", "episode", "time_bucket_hours", "first_datetime"])
            .agg(
                [
                    pl.col("downloads_delta").sum().alias("downloads_period"),
                    pl.col("datetime").min().alias("period_start"),
                ]
            )
            .sort(["anilist_id", "episode", "time_bucket_hours"])
        )

        # Calculate cumulative downloads per episode
        stats = stats.with_columns(
            pl.col("downloads_period")
            .cum_sum()
            .over(["anilist_id", "episode"])
            .alias("downloads_cumulative")
        )

        # Convert time_bucket_hours to days for output
        stats = stats.with_columns(
            (pl.col("time_bucket_hours") / 24).alias("days_since_first_torrent")
        )

        # Also keep the date for compatibility with weekly rankings
        stats = stats.with_columns(
            pl.col("period_start").dt.date().alias("date")
        )

        # Rename downloads_period to downloads_daily for compatibility
        stats = stats.rename({"downloads_period": "downloads_daily"})

        # Add show titles and cover images
        show_lookup = {
            show.id: {
                "title_romaji": show.title_romaji,
                "title_english": show.title_english or show.title_romaji,
                "cover_image_url": show.cover_image_url,
                "cover_image_color": show.cover_image_color,
            }
            for show in shows
        }

        default_show = {
            "title_romaji": "Unknown",
            "title_english": "Unknown",
            "cover_image_url": None,
            "cover_image_color": None,
        }

        stats = stats.with_columns(
            [
                pl.col("anilist_id")
                .map_elements(
                    lambda aid: show_lookup.get(aid, default_show)["title_romaji"],
                    return_dtype=pl.Utf8,
                )
                .alias("title"),
                pl.col("anilist_id")
                .map_elements(
                    lambda aid: show_lookup.get(aid, default_show)["title_english"],
                    return_dtype=pl.Utf8,
                )
                .alias("title_english"),
                pl.col("anilist_id")
                .map_elements(
                    lambda aid: show_lookup.get(aid, default_show)["cover_image_url"],
                    return_dtype=pl.Utf8,
                )
                .alias("cover_image_url"),
                pl.col("anilist_id")
                .map_elements(
                    lambda aid: show_lookup.get(aid, default_show)["cover_image_color"],
                    return_dtype=pl.Utf8,
                )
                .alias("cover_image_color"),
            ]
        )

        logger.info(
            f"Aggregated {len(stats)} episode stats "
            f"for {stats['anilist_id'].n_unique()} shows"
        )

        return stats

    def calculate_weekly_rankings(
        self, daily_stats: pl.DataFrame, shows: list[AniListShow]
    ) -> pl.DataFrame:
        """Calculate weekly rankings from daily stats.

        Args:
            daily_stats: Daily episode stats
            shows: List of AniList shows for metadata

        Returns:
            DataFrame with weekly rankings
        """
        # Extract ISO week from date
        # Use %G-%V for true ISO week (week 1 = first week with Thursday of new year)
        daily_stats = daily_stats.with_columns(
            [
                pl.col("date")
                .cast(pl.Datetime("us"))
                .dt.strftime("%G-W%V")
                .alias("iso_week"),
            ]
        )

        # Aggregate downloads by (anilist_id, iso_week)
        weekly_totals = (
            daily_stats.group_by([
                "anilist_id", "iso_week", "title", "title_english",
                "cover_image_url", "cover_image_color"
            ])
            .agg([pl.col("downloads_daily").sum().alias("downloads")])
            .sort(["iso_week", "downloads"], descending=[False, True])
        )

        # Rank within each week
        weekly_totals = weekly_totals.with_columns(
            pl.col("downloads")
            .rank(method="ordinal", descending=True)
            .over("iso_week")
            .alias("rank")
        )

        logger.info(
            f"Calculated weekly rankings for {weekly_totals['iso_week'].n_unique()} weeks"
        )

        return weekly_totals.select(
            [
                pl.col("iso_week").alias("week"),
                "anilist_id",
                "rank",
                "downloads",
                pl.col("title_english").alias("title"),
                pl.col("title").alias("title_romaji"),
                "cover_image_url",
                "cover_image_color",
            ]
        )

    def close(self):
        """Close database connection."""
        if hasattr(self, 'sqlite_conn') and self.sqlite_conn:
            self.sqlite_conn.close()
