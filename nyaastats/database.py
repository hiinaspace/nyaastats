import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from .models import GuessitData, StatsData, TorrentData

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS torrents (
    infohash TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    pubdate TIMESTAMP NOT NULL,
    size_bytes INTEGER,
    nyaa_id INTEGER,
    trusted BOOLEAN DEFAULT 0,
    remake BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Guessit fields
    title TEXT,
    alternative_title TEXT,
    episode INTEGER,
    season INTEGER,
    year INTEGER,
    release_group TEXT,
    resolution TEXT,
    video_codec TEXT,
    audio_codec TEXT,
    source TEXT,
    container TEXT,
    language TEXT,
    subtitles TEXT,
    other TEXT
);

CREATE TABLE IF NOT EXISTS stats (
    infohash TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    seeders INTEGER NOT NULL,
    leechers INTEGER NOT NULL,
    downloads INTEGER NOT NULL,
    PRIMARY KEY (infohash, timestamp),
    FOREIGN KEY (infohash) REFERENCES torrents(infohash)
);

CREATE INDEX IF NOT EXISTS idx_stats_infohash ON stats(infohash);
CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_torrents_pubdate ON torrents(pubdate);
CREATE INDEX IF NOT EXISTS idx_torrents_status ON torrents(status);
"""


class Database:
    def __init__(self, db_path: str = "nyaastats.db"):
        self.db_path = db_path
        self._memory_conn = None
        self.init_db()

    def init_db(self) -> None:
        """Initialize the database with schema."""
        with self.get_conn() as conn:
            # Only enable WAL mode for file-based databases, not in-memory
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")

            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def get_conn(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with row factory."""
        if self.db_path == ":memory:":
            # For in-memory databases, maintain a persistent connection
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(self.db_path)
                self._memory_conn.row_factory = sqlite3.Row
            yield self._memory_conn
        else:
            # For file databases, create new connections as needed
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def insert_torrent(
        self, torrent_data: TorrentData, guessit_data: GuessitData
    ) -> None:
        """Insert a torrent with metadata and initial stats."""
        with self.get_conn() as conn:
            # Convert guessit_data to dict for processing
            guessit_dict = guessit_data.model_dump()

            # Insert torrent metadata
            conn.execute(
                """
                INSERT OR IGNORE INTO torrents (
                    infohash, filename, pubdate, size_bytes, nyaa_id,
                    trusted, remake, title, episode, season, year,
                    release_group, resolution, video_codec, audio_codec,
                    source, container, language, subtitles, other
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    torrent_data.infohash,
                    torrent_data.filename,
                    torrent_data.pubdate,
                    torrent_data.size_bytes,
                    torrent_data.nyaa_id,
                    torrent_data.trusted,
                    torrent_data.remake,
                    guessit_data.title,
                    guessit_data.episode,
                    guessit_data.season,
                    guessit_data.year,
                    guessit_data.release_group,
                    guessit_data.resolution,
                    guessit_data.video_codec,
                    guessit_data.audio_codec,
                    guessit_data.source,
                    guessit_data.container,
                    guessit_data.language,
                    json.dumps(guessit_data.subtitles or []),
                    json.dumps(
                        {
                            k: v
                            for k, v in guessit_dict.items()
                            if k
                            not in [
                                "title",
                                "alternative_title",
                                "episode",
                                "season",
                                "year",
                                "release_group",
                                "resolution",
                                "video_codec",
                                "audio_codec",
                                "source",
                                "container",
                                "language",
                                "subtitles",
                            ]
                        }
                    ),
                ),
            )

            # Insert initial stats from RSS
            conn.execute(
                """
                INSERT OR IGNORE INTO stats (infohash, timestamp, seeders, leechers, downloads)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    torrent_data.infohash,
                    torrent_data.pubdate,
                    torrent_data.seeders,
                    torrent_data.leechers,
                    torrent_data.downloads,
                ),
            )

            conn.commit()

    def insert_stats(
        self, infohash: str, stats: StatsData, timestamp: datetime | None = None
    ) -> None:
        """Insert statistics for a torrent."""
        if timestamp is None:
            timestamp = datetime.utcnow()

        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO stats (infohash, timestamp, seeders, leechers, downloads)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    infohash,
                    timestamp,
                    stats.seeders,
                    stats.leechers,
                    stats.downloads,
                ),
            )
            conn.commit()

    def mark_torrent_status(self, infohash: str, status: str) -> None:
        """Mark a torrent with a specific status."""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE torrents SET status = ? WHERE infohash = ?",
                (status, infohash),
            )
            conn.commit()

    def get_torrent_exists(self, infohash: str) -> bool:
        """Check if a torrent exists in the database."""
        with self.get_conn() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM torrents WHERE infohash = ?",
                (infohash,),
            )
            return cursor.fetchone() is not None

    def get_recent_stats(self, infohash: str, limit: int = 3) -> list[dict[str, Any]]:
        """Get recent statistics for a torrent."""
        with self.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT seeders, leechers, downloads, timestamp
                FROM stats
                WHERE infohash = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (infohash, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def vacuum(self) -> None:
        """Vacuum the database for maintenance."""
        with self.get_conn() as conn:
            conn.execute("VACUUM")
            conn.commit()
