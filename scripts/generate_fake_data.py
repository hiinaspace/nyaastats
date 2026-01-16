#!/usr/bin/env python3
"""Generate fake nyaastats.db for development and testing.

Creates realistic synthetic data for Fall 2025 (complete season) and Winter 2026
(currently airing season) to test the ETL pipeline and website without needing
the production database.
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import timedelta
from pathlib import Path

# Add parent directory to path to import nyaastats modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from whenever import Instant

from nyaastats.database import Database
from nyaastats.models import TorrentData


# Realistic anime titles for test data
FALL_2025_SHOWS = [
    "Dungeon Meshi S2",
    "Frieren: Beyond Journey's End S2",
    "Chainsaw Man S2",
    "Spy x Family S3",
    "My Hero Academia S8",
    "Demon Slayer S5",
    "Blue Lock S2",
    "Vinland Saga S3",
    "Jujutsu Kaisen S3",
    "Mob Psycho 100 III",
    "Attack on Titan: Final Season Part 4",
    "Tokyo Revengers S4",
    "Dr. Stone S4",
    "The Eminence in Shadow S3",
    "Mushoku Tensei S3",
]

WINTER_2026_SHOWS = [
    "Solo Leveling S2",
    "Demon Slayer S6",
    "The Apothecary Diaries S2",
    "Kusuriya no Hitorigoto S2",
    "Wind Breaker",
    "Delicious in Dungeon S3",
    "Dandadan S2",
    "Blue Exorcist S4",
    "Haikyuu!! Final",
    "Re:Zero S3",
    "Overlord V",
    "Kaguya-sama S4",
    "Horimiya S3",
    "Oshi no Ko S3",
    "86 Eighty-Six S3",
]

RELEASE_GROUPS = ["SubsPlease", "Erai-raws", "Judas", "Tsundere-Raws", "HorribleSubs"]
RESOLUTIONS = ["1080p", "720p", "480p"]

# Season date ranges
FALL_2025_START = Instant.from_utc(2025, 10, 1)
FALL_2025_END = Instant.from_utc(2025, 12, 25)
WINTER_2026_START = Instant.from_utc(2026, 1, 5)
WINTER_2026_NOW = Instant.from_utc(2026, 1, 16)  # Current date


def normalize_title_for_hash(title: str) -> str:
    """Normalize title for generating consistent infohash."""
    return title.lower().replace(" ", "").replace(":", "")


def generate_infohash(show_title: str, episode: int, group: str, resolution: str) -> str:
    """Generate a deterministic fake infohash."""
    content = f"{normalize_title_for_hash(show_title)}_{episode}_{group}_{resolution}"
    return hashlib.sha1(content.encode()).hexdigest()


def generate_filename(show_title: str, episode: int, group: str, resolution: str) -> str:
    """Generate a realistic torrent filename that guessit can parse."""
    # Format: [Group] Show Title - EP [Resolution].mkv
    return f"[{group}] {show_title} - {episode:02d} [{resolution}].mkv"


def generate_guessit_data(show_title: str, episode: int, group: str, resolution: str) -> dict:
    """Generate realistic guessit metadata."""
    # Split title into base title and season if present
    title_parts = show_title.rsplit(" S", 1)
    base_title = title_parts[0]

    # Extract season number with error handling
    season = 1
    if len(title_parts) > 1:
        try:
            season = int(title_parts[1])
        except (ValueError, TypeError):
            # If season extraction fails, default to 1
            season = 1

    return {
        "title": base_title,
        "episode": episode,
        "season": season,
        "release_group": group,
        "screen_size": resolution,
        "type": "episode",
        "source": "Web",
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "container": "mkv",
    }


def generate_download_curve(
    first_timestamp: Instant,
    end_timestamp: Instant,
    peak_downloads: int,
    sample_interval_hours: int = 24,
) -> list[tuple[Instant, int]]:
    """Generate realistic download curve with exponential decay.

    Downloads spike at release and decay exponentially over time.
    Returns list of (timestamp, cumulative_downloads) tuples.
    """
    curve = []
    current_time = first_timestamp
    cumulative_downloads = 0

    # Time since release in hours
    hours_since_release = 0

    while current_time <= end_timestamp:
        # Exponential decay: high downloads in first 24h, then tapering
        # Peak in first 12 hours, then decay with half-life of ~48 hours
        if hours_since_release < 12:
            downloads_rate = peak_downloads * 0.4  # 40% in first 12h
        elif hours_since_release < 24:
            downloads_rate = peak_downloads * 0.2  # 20% in next 12h
        elif hours_since_release < 72:
            downloads_rate = peak_downloads * 0.15  # 15% in next 48h
        else:
            # Exponential decay after 72h
            decay_factor = 0.96 ** ((hours_since_release - 72) / 24)
            downloads_rate = peak_downloads * 0.05 * decay_factor

        # Convert rate to downloads in this interval
        interval_downloads = int(downloads_rate * (sample_interval_hours / 24))
        interval_downloads = max(0, int(random.gauss(interval_downloads, interval_downloads * 0.1)))

        cumulative_downloads += interval_downloads
        curve.append((current_time, cumulative_downloads))

        current_time = current_time.add(hours=sample_interval_hours)
        hours_since_release += sample_interval_hours

    return curve


def generate_show_data(
    db: Database,
    show_title: str,
    num_episodes: int,
    air_start_date: Instant,
    season_end_date: Instant,
    is_complete: bool,
    quick: bool = False,
):
    """Generate all torrents and stats for one show.

    Args:
        db: Database instance
        show_title: Show title
        num_episodes: Total number of episodes
        air_start_date: When first episode airs
        season_end_date: End of season (for post-airing downloads)
        is_complete: If True, all episodes have aired. If False, only some episodes.
        quick: If True, generate fewer versions per episode
    """
    # Determine how many episodes to generate
    if is_complete:
        episodes_to_generate = num_episodes
    else:
        # For ongoing shows, only generate episodes up to current date
        # Assume weekly airing (7 days between episodes)
        weeks_since_start = (WINTER_2026_NOW - air_start_date).in_seconds() / (7 * 86400)
        episodes_to_generate = min(num_episodes, int(weeks_since_start) + 1)

    # Generate torrents for each episode with multiple versions
    for episode in range(1, episodes_to_generate + 1):
        # Episode air date (weekly releases)
        episode_air_date = air_start_date.add(hours=(episode - 1) * 7 * 24)

        # Determine end date for this episode's download tracking
        if is_complete:
            # Complete show: track downloads until season end + 4 weeks
            episode_end_date = season_end_date.add(hours=28 * 24)
        else:
            # Ongoing show: track until current date
            episode_end_date = WINTER_2026_NOW

        # Generate multiple versions (different groups/resolutions)
        # In quick mode, generate fewer versions per episode for speed
        num_groups = 1 if quick else random.randint(2, 3)
        num_resolutions = 1 if quick else random.randint(1, 2)

        for group in random.sample(RELEASE_GROUPS, k=num_groups):
            for resolution in random.sample(RESOLUTIONS, k=num_resolutions):
                infohash = generate_infohash(show_title, episode, group, resolution)
                filename = generate_filename(show_title, episode, group, resolution)
                guessit_data = generate_guessit_data(show_title, episode, group, resolution)

                # Torrent appears 2-6 hours after episode airs (fansub delay)
                torrent_pubdate = episode_air_date.add(hours=random.randint(2, 6))

                # Skip future torrents
                if torrent_pubdate > WINTER_2026_NOW:
                    continue

                # Base download count varies by resolution and group
                if resolution == "1080p":
                    base_downloads = random.randint(3000, 8000)
                elif resolution == "720p":
                    base_downloads = random.randint(2000, 5000)
                else:
                    base_downloads = random.randint(500, 1500)

                # Popular groups get more downloads
                if group in ["SubsPlease", "Erai-raws"]:
                    base_downloads = int(base_downloads * 1.5)

                # Create torrent entry
                torrent_data = TorrentData(
                    infohash=infohash,
                    filename=filename,
                    pubdate=torrent_pubdate,
                    size_bytes=random.randint(300_000_000, 1_500_000_000),  # 300MB-1.5GB
                    nyaa_id=random.randint(1000000, 9999999),
                    trusted=group in ["SubsPlease", "Erai-raws"],
                    remake=False,
                    seeders=random.randint(50, 500),
                    leechers=random.randint(5, 50),
                    downloads=0,  # Initial downloads (will be set by first stats entry)
                    guessit_data=guessit_data,
                )

                db.insert_torrent(torrent_data)

                # Generate download curve stats
                download_curve = generate_download_curve(
                    torrent_pubdate,
                    episode_end_date,
                    base_downloads,
                    sample_interval_hours=24,
                )

                # Batch insert all stats for this torrent
                with db.get_conn() as conn:
                    for timestamp, cumulative_downloads in download_curve:
                        # Seeders and leechers decay over time too
                        days_since_release = (timestamp - torrent_pubdate).in_seconds() / 86400
                        seeders = max(5, int(500 * (0.95 ** days_since_release)) + random.randint(-10, 10))
                        leechers = max(0, int(50 * (0.90 ** days_since_release)) + random.randint(-5, 5))

                        conn.execute(
                            """
                            INSERT OR REPLACE INTO stats (infohash, timestamp, seeders, leechers, downloads)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (infohash, timestamp, seeders, leechers, cumulative_downloads),
                        )
                    # Commit once per torrent instead of once per stat entry
                    conn.commit()


def generate_fake_database(db_path: str, verbose: bool = False, quick: bool = False):
    """Generate a complete fake database.

    Args:
        db_path: Path to output database
        verbose: Print detailed progress
        quick: Generate smaller dataset (5 shows per season) for faster testing
    """
    print(f"Generating fake database at: {db_path}")

    # Remove existing database
    Path(db_path).unlink(missing_ok=True)

    # Create new database
    db = Database(db_path)

    # Select subset of shows if in quick mode
    fall_shows = FALL_2025_SHOWS[:5] if quick else FALL_2025_SHOWS
    winter_shows = WINTER_2026_SHOWS[:5] if quick else WINTER_2026_SHOWS

    # Generate Fall 2025 shows (complete season)
    print(f"\nGenerating Fall 2025 shows (complete)... {len(fall_shows)} shows")
    for i, show_title in enumerate(fall_shows):
        num_episodes = random.randint(12, 13)  # Standard seasonal length
        # Stagger air dates throughout the season
        days_offset = (i * 2) % 7  # Different days of the week
        air_start = FALL_2025_START.add(hours=days_offset * 24)

        if verbose:
            print(f"  - {show_title} ({num_episodes} episodes)")

        generate_show_data(
            db,
            show_title,
            num_episodes,
            air_start,
            FALL_2025_END,
            is_complete=True,
            quick=quick,
        )

    # Generate Winter 2026 shows (currently airing)
    print(f"\nGenerating Winter 2026 shows (currently airing)... {len(winter_shows)} shows")
    for i, show_title in enumerate(winter_shows):
        num_episodes = random.randint(12, 13)
        days_offset = (i * 2) % 7
        air_start = WINTER_2026_START.add(hours=days_offset * 24)

        if verbose:
            weeks_aired = (WINTER_2026_NOW - air_start).in_seconds() / (7 * 86400)
            episodes_so_far = min(num_episodes, int(weeks_aired) + 1)
            print(f"  - {show_title} ({episodes_so_far}/{num_episodes} episodes so far)")

        generate_show_data(
            db,
            show_title,
            num_episodes,
            air_start,
            WINTER_2026_NOW,
            is_complete=False,
            quick=quick,
        )

    # Print summary statistics
    with db.get_conn() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM torrents")
        torrent_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM stats")
        stats_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM stats")
        min_date, max_date = cursor.fetchone()

    print("\n" + "=" * 60)
    print("Fake database generated successfully!")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Torrents: {torrent_count:,}")
    print(f"Stats entries: {stats_count:,}")
    print(f"Date range: {min_date} to {max_date}")
    print(f"Fall 2025 shows: {len(fall_shows)} (complete)")
    print(f"Winter 2026 shows: {len(winter_shows)} (airing)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate fake nyaastats.db for development"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="nyaastats_fake.db",
        help="Output database path (default: nyaastats_fake.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed progress",
    )
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Generate smaller dataset (5 shows per season) for faster testing",
    )
    args = parser.parse_args()

    generate_fake_database(args.output, args.verbose, args.quick)


if __name__ == "__main__":
    main()
