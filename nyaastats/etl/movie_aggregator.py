"""Movie-specific download aggregation (no episode dimension)."""

import logging

import polars as pl

from .aggregator import DownloadAggregator
from .anilist_client import AniListShow
from .fuzzy_matcher import TitleMatch

logger = logging.getLogger(__name__)


class MovieAggregator:
    """Aggregates download stats for movies using an existing DownloadAggregator."""

    def __init__(self, aggregator: DownloadAggregator):
        self.aggregator = aggregator

    def load_movie_torrents(
        self, min_date: str, matched_torrents: dict[str, TitleMatch]
    ) -> pl.DataFrame:
        """Load torrents matched to movies from database.

        Unlike TV episodes, movies don't require an episode number.
        Some movie torrents may have episode numbers (multi-part releases).

        Args:
            min_date: ISO date string for earliest torrent
            matched_torrents: Dict mapping infohash to TitleMatch

        Returns:
            Polars DataFrame with movie torrents and metadata
        """
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

        df = pl.read_database(query, connection=self.aggregator.sqlite_conn)
        logger.info(f"Loaded {len(df)} torrents for movie matching")

        # Filter to matched movie torrents only
        matched_infohashes = set(matched_torrents.keys())
        df = df.filter(pl.col("infohash").is_in(matched_infohashes))

        logger.info(f"After filtering to matched movies: {len(df)} torrents")

        # Add anilist_id from matches
        df = df.with_columns(
            pl.col("infohash")
            .map_elements(
                lambda h: matched_torrents[h].anilist_id
                if h in matched_torrents
                else None,
                return_dtype=pl.Int64,
            )
            .alias("anilist_id")
        )

        return df

    def aggregate_movie_downloads(
        self,
        torrents_df: pl.DataFrame,
        deltas_df: pl.DataFrame,
        movie_shows: list[AniListShow],
    ) -> pl.DataFrame:
        """Aggregate downloads by (anilist_id, week) — no episode dimension.

        Uses 7-day buckets since scraping frequency for older movies is weekly.
        Each bucket has both weeks_since_release (aligned to first torrent)
        and an absolute week_start date for the absolute-time chart.

        Args:
            torrents_df: Filtered movie torrents with metadata
            deltas_df: Download deltas
            movie_shows: List of AniList movie shows for metadata

        Returns:
            DataFrame with movie download stats in weekly buckets
        """
        # Join torrents with deltas
        combined = deltas_df.join(
            torrents_df.select(["infohash", "anilist_id", "pubdate"]),
            on="infohash",
            how="inner",
        )

        if len(combined) == 0:
            logger.warning("No movie download data found after join")
            return pl.DataFrame(
                {
                    "anilist_id": [],
                    "weeks_since_release": [],
                    "downloads_weekly": [],
                    "downloads_cumulative": [],
                }
            )

        # Parse timestamp
        combined = combined.with_columns(
            pl.col("timestamp")
            .str.to_datetime(format="%+", time_zone="UTC")
            .alias("datetime"),
        )

        # Find first torrent timestamp per movie
        first_torrent = torrents_df.group_by("anilist_id").agg(
            pl.col("pubdate").min().alias("first_torrent_timestamp")
        )

        first_torrent = first_torrent.with_columns(
            pl.col("first_torrent_timestamp")
            .str.to_datetime(format="%+", time_zone="UTC")
            .alias("first_datetime")
        )

        combined = combined.join(
            first_torrent.select(["anilist_id", "first_datetime"]),
            on="anilist_id",
            how="left",
        )

        # Calculate weeks since first torrent (7-day buckets)
        combined = combined.with_columns(
            (
                (pl.col("datetime") - pl.col("first_datetime")).dt.total_seconds()
                / (86400 * 7)
            )
            .floor()
            .cast(pl.Int64)
            .alias("weeks_since_release")
        )

        # Also compute absolute ISO week (Monday-based) for the weekly chart
        combined = combined.with_columns(
            pl.col("datetime").dt.truncate("1w").dt.date().alias("week_start")
        )

        # Aggregate by (anilist_id, weeks_since_release)
        stats = (
            combined.group_by(["anilist_id", "weeks_since_release"])
            .agg(
                [
                    pl.col("downloads_delta").sum().alias("downloads_weekly"),
                    pl.col("week_start").min().alias("week_start"),
                ]
            )
            .sort(["anilist_id", "weeks_since_release"])
        )

        # Calculate cumulative downloads per movie
        stats = stats.with_columns(
            pl.col("downloads_weekly")
            .cum_sum()
            .over("anilist_id")
            .alias("downloads_cumulative")
        )

        # Add show metadata
        show_lookup = {
            show.id: {
                "title_romaji": show.title_romaji,
                "title_english": show.title_english or show.title_romaji,
                "cover_image_url": show.cover_image_url,
                "cover_image_color": show.cover_image_color,
            }
            for show in movie_shows
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

        # Add first torrent date
        stats = stats.join(
            first_torrent.select(["anilist_id", "first_datetime"]),
            on="anilist_id",
            how="left",
        )

        logger.info(
            f"Aggregated movie stats for {stats['anilist_id'].n_unique()} movies"
        )

        return stats
