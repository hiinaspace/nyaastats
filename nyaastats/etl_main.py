"""Main ETL pipeline for nyaastats analytics."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import polars as pl

from nyaastats.etl.aggregator import DownloadAggregator
from nyaastats.etl.anilist_client import fetch_all_seasons
from nyaastats.etl.config import MVP_SEASONS
from nyaastats.etl.exporter import DataExporter
from nyaastats.etl.fuzzy_matcher import FuzzyMatcher
from nyaastats.etl.seasonal_exporter import SeasonalExporter
from nyaastats.etl.title_corrections import apply_title_corrections

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_etl_pipeline(
    db_path: str,
    output_dir: str,
    fuzzy_threshold: int = 85,
    use_mock_anilist: bool = False,
):
    """Run the complete ETL pipeline.

    Args:
        db_path: Path to nyaastats SQLite database
        output_dir: Directory to write output files
        fuzzy_threshold: Minimum fuzzy match score (0-100)
        use_mock_anilist: Use mock AniList data instead of real API
    """
    logger.info("=" * 80)
    logger.info("Starting nyaastats ETL pipeline")
    logger.info("=" * 80)

    # Step 1: Fetch AniList data
    if use_mock_anilist:
        logger.info("\nStep 1: Using mock AniList data (--mock-anilist enabled)...")
        from nyaastats.etl.mock_data import get_mock_seasons_data

        seasons_data = get_mock_seasons_data()
    else:
        logger.info("\nStep 1: Fetching anime metadata from AniList...")
        seasons_data = await fetch_all_seasons(MVP_SEASONS)

    all_shows = []
    for season_name, shows in seasons_data.items():
        logger.info(f"  {season_name}: {len(shows)} shows")
        all_shows.extend(shows)

    # Step 2: Load torrents from database
    logger.info("\nStep 2: Loading torrents from database...")
    aggregator = DownloadAggregator(db_path)

    try:
        # Get all torrents for initial fuzzy matching
        query = f"""
        SELECT
            infohash,
            guessit_data
        FROM torrents
        WHERE pubdate >= '{MVP_SEASONS[0].start_date.format_common_iso()}'
            AND (status IS NULL OR status != 'guessit_failed')
            AND guessit_data IS NOT NULL
        """

        torrents_raw = pl.read_database(query, connection=aggregator.sqlite_conn)
        logger.info(f"Loaded {len(torrents_raw)} torrents")

        # Parse guessit data to extract metadata for fuzzy matching
        import json

        def extract_metadata(guessit_json: str) -> dict:
            """Extract title, season, and episode from guessit JSON.

            Returns:
                Dict with 'title', 'season', and 'episode' keys (all may be None)
            """
            try:
                data = json.loads(guessit_json)
                title = data.get("title")
                season = data.get("season")
                episode = data.get("episode")

                # Apply title corrections to fix guessit parsing errors
                corrected_title = apply_title_corrections(title)

                # Only use integer seasons, skip arrays (batch releases like [1,2,3])
                season_int = season if isinstance(season, int) else None

                # For episodes, handle both single int and lists (take first if list)
                if isinstance(episode, list) and len(episode) > 0:
                    episode_int = episode[0] if isinstance(episode[0], int) else None
                elif isinstance(episode, int):
                    episode_int = episode
                else:
                    episode_int = None

                return {
                    "title": corrected_title,
                    "season": season_int,
                    "episode": episode_int,
                }
            except Exception:
                # Return dict with None values instead of None itself
                # This ensures polars can always extract struct fields
                return {
                    "title": None,
                    "season": None,
                    "episode": None,
                }

        # Define struct schema for metadata extraction
        metadata_schema = pl.Struct(
            [
                pl.Field("title", pl.Utf8),
                pl.Field("season", pl.Int64),
                pl.Field("episode", pl.Int64),
            ]
        )

        torrents_raw = torrents_raw.with_columns(
            [
                pl.col("guessit_data")
                .map_elements(extract_metadata, return_dtype=metadata_schema)
                .alias("metadata"),
            ]
        ).with_columns(
            [
                pl.col("metadata").struct.field("title").alias("title"),
                pl.col("metadata").struct.field("season").alias("season"),
                pl.col("metadata").struct.field("episode").alias("episode"),
            ]
        )

        # Filter to valid titles
        torrents_for_matching = torrents_raw.filter(pl.col("title").is_not_null())

        # Step 3: Fuzzy match torrent titles to AniList shows
        logger.info("\nStep 3: Fuzzy matching torrent titles to AniList shows...")
        matcher = FuzzyMatcher(all_shows, threshold=fuzzy_threshold)

        # Prepare batch for matching (with season info)
        title_batch = [
            (row["infohash"], row["title"], row["season"], row["episode"])
            for row in torrents_for_matching.iter_rows(named=True)
        ]

        matched, unmatched = matcher.match_batch(title_batch)

        # Convert matched list to dict for easier lookup
        matched_dict = dict(matched)

        # Generate unmatched torrents report for investigation
        logger.info("\nGenerating unmatched torrents report...")
        if unmatched:
            # Get download stats for unmatched torrents
            unmatched_infohashes = [infohash for infohash, _, _ in unmatched]
            unmatched_stats_query = f"""
            SELECT
                t.infohash,
                t.filename,
                json_extract(t.guessit_data, '$.title') as guessit_title,
                json_extract(t.guessit_data, '$.season') as season,
                json_extract(t.guessit_data, '$.episode') as episode,
                MAX(s.downloads) as max_downloads,
                COUNT(s.timestamp) as stat_count
            FROM torrents t
            LEFT JOIN stats s ON t.infohash = s.infohash
            WHERE t.infohash IN ({",".join(["?"] * len(unmatched_infohashes))})
            GROUP BY t.infohash
            ORDER BY max_downloads DESC
            LIMIT 100
            """
            # Use parameterized query directly
            cursor = aggregator.sqlite_conn.cursor()
            cursor.execute(unmatched_stats_query, unmatched_infohashes)
            rows = cursor.fetchall()

            # Convert to dataframe manually
            unmatched_df = pl.DataFrame(
                {
                    "infohash": [r[0] for r in rows],
                    "filename": [r[1] for r in rows],
                    "guessit_title": [r[2] for r in rows],
                    "season": [r[3] for r in rows],
                    "episode": [r[4] for r in rows],
                    "max_downloads": [r[5] for r in rows],
                    "stat_count": [r[6] for r in rows],
                }
            )

            # Export unmatched report
            import json
            from pathlib import Path

            report_data = []
            for row in unmatched_df.iter_rows(named=True):
                report_data.append(
                    {
                        "filename": row["filename"],
                        "guessit_title": row["guessit_title"],
                        "season": row["season"],
                        "episode": row["episode"],
                        "max_downloads": row["max_downloads"],
                        "stat_count": row["stat_count"],
                    }
                )

            report_path = Path(output_dir) / "unmatched_torrents_report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                json.dump(report_data, f, indent=2)

            logger.info(
                f"Exported unmatched torrents report to {report_path} "
                f"({len(report_data)} torrents)"
            )

            # Log top 10 unmatched by downloads
            logger.info("\nTop 10 unmatched torrents by download count:")
            for i, item in enumerate(report_data[:10], 1):
                logger.info(
                    f"  {i}. {item['guessit_title']} (S{item['season']}E{item['episode']}) "
                    f"- {item['max_downloads']:,} downloads - {item['filename'][:60]}..."
                )

        # Step 4: Filter and aggregate downloads
        logger.info("\nStep 4: Filtering and aggregating download stats...")
        torrents_df = aggregator.load_and_filter_torrents(MVP_SEASONS, matched_dict)

        if len(torrents_df) == 0:
            logger.error("No matched torrents found! Check fuzzy matching threshold.")
            return

        logger.info("\nStep 5: Calculating download deltas...")
        deltas_df = aggregator.calculate_download_deltas(torrents_df)

        logger.info("\nStep 6: Aggregating by episode and date...")
        daily_stats = aggregator.aggregate_by_episode_and_date(
            torrents_df, deltas_df, all_shows
        )

        logger.info("\nStep 7: Calculating weekly rankings...")
        weekly_rankings = aggregator.calculate_weekly_rankings(daily_stats, all_shows)

        # Step 8: Export results
        logger.info("\nStep 8: Exporting results...")
        exporter = DataExporter(output_dir)

        exporter.export_weekly_rankings(weekly_rankings)

        # Step 9: Export seasonal summary data for interactive visualizations
        logger.info("\nStep 9: Exporting seasonal summary data...")
        seasonal_exporter = SeasonalExporter(output_dir)

        for season_config in MVP_SEASONS:
            # Get show IDs for this season from AniList metadata
            season_show_ids = [
                show.id for show in seasons_data.get(season_config.name, [])
            ]
            if not season_show_ids:
                logger.warning(f"No shows found for {season_config.name}, skipping")
                continue

            seasonal_exporter.export_season_summary(
                season_config, weekly_rankings, daily_stats, season_show_ids
            )
            seasonal_exporter.export_season_episodes(
                season_config, daily_stats, season_show_ids
            )

        seasonal_exporter.export_seasons_index(
            MVP_SEASONS, seasons_data, weekly_rankings
        )

        logger.info("\n" + "=" * 80)
        logger.info("ETL pipeline completed successfully!")
        logger.info("=" * 80)
        logger.info(f"Outputs written to: {output_dir}")
        logger.info(f"  - rankings.json: {weekly_rankings['week'].n_unique()} weeks")
        logger.info("  - seasons.json: season index")
        logger.info("  - season-*.json: Seasonal summary data")
        logger.info("  - episodes-*.json: Season episode totals")
    finally:
        # Ensure database connection is always closed
        aggregator.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run nyaastats ETL pipeline to generate analytics outputs"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="nyaastats.db",
        help="Path to nyaastats SQLite database (default: nyaastats.db)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output",
        help="Output directory for generated files (default: output/)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=int,
        default=85,
        help="Minimum fuzzy match score 0-100 (default: 85)",
    )
    parser.add_argument(
        "--mock-anilist",
        action="store_true",
        help="Use mock AniList data instead of querying real API (for testing)",
    )

    args = parser.parse_args()

    # Check database exists
    if not Path(args.db).exists():
        logger.error(f"Database not found: {args.db}")
        sys.exit(1)

    # Run pipeline
    try:
        asyncio.run(
            run_etl_pipeline(
                db_path=args.db,
                output_dir=args.output,
                fuzzy_threshold=args.fuzzy_threshold,
                use_mock_anilist=args.mock_anilist,
            )
        )
    except Exception:
        logger.exception("ETL pipeline failed with error:")
        sys.exit(1)


if __name__ == "__main__":
    main()
