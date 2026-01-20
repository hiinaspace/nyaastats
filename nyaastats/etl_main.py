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

        # Parse guessit data to extract titles (only need title for fuzzy matching)
        import json

        def extract_title(guessit_json: str) -> str | None:
            """Extract title from guessit JSON for fuzzy matching."""
            try:
                data = json.loads(guessit_json)
                return data.get("title")
            except Exception:
                return None

        torrents_raw = torrents_raw.with_columns(
            [
                pl.col("guessit_data")
                .map_elements(extract_title, return_dtype=pl.Utf8)
                .alias("title"),
            ]
        )

        # Filter to valid titles
        torrents_for_matching = torrents_raw.filter(pl.col("title").is_not_null())

        # Step 3: Fuzzy match torrent titles to AniList shows
        logger.info("\nStep 3: Fuzzy matching torrent titles to AniList shows...")
        matcher = FuzzyMatcher(all_shows, threshold=fuzzy_threshold)

        # Prepare batch for matching
        title_batch = [
            (row["infohash"], row["title"])
            for row in torrents_for_matching.iter_rows(named=True)
        ]

        matched, unmatched = matcher.match_batch(title_batch)

        # Convert matched list to dict for easier lookup
        matched_dict = {infohash: match for infohash, match in matched}

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
