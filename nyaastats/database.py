import json
import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from whenever import Instant

from .models import StatsData, TorrentData

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS torrents (
    infohash TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    pubdate TEXT NOT NULL,
    size_bytes INTEGER,
    nyaa_id INTEGER,
    trusted BOOLEAN DEFAULT 0,
    remake BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'active',

    -- Guessit data as JSON
    guessit_data TEXT
);

CREATE TABLE IF NOT EXISTS stats (
    infohash TEXT NOT NULL,
    timestamp TEXT NOT NULL,
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
    def __init__(
        self,
        db_path: str = "nyaastats.db",
        now_func: Callable[[], Instant] = Instant.now,
    ):
        self.db_path = db_path
        self._memory_conn = None
        self.now_func = now_func
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
                self._memory_conn = sqlite3.connect(
                    self.db_path, detect_types=sqlite3.PARSE_DECLTYPES
                )
                self._memory_conn.row_factory = sqlite3.Row
                self._register_adapters_converters(self._memory_conn)
            yield self._memory_conn
        else:
            # For file databases, create new connections as needed
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            conn.row_factory = sqlite3.Row
            self._register_adapters_converters(conn)
            try:
                yield conn
            finally:
                conn.close()

    def _register_adapters_converters(self, conn: sqlite3.Connection) -> None:
        """Register adapters and converters for custom types."""

        # Register Instant adapter and converter
        def adapt_instant(instant: Instant) -> str:
            # Use common ISO format that SQLite can understand and we can parse
            return instant.format_common_iso()

        def convert_instant(s: bytes) -> Instant:
            timestamp_str = s.decode()
            return Instant.parse_common_iso(timestamp_str)

        # Register with sqlite3
        sqlite3.register_adapter(Instant, adapt_instant)
        sqlite3.register_converter("TIMESTAMP", convert_instant)

    def insert_torrent(self, torrent_data: TorrentData) -> None:
        """Insert a torrent with metadata and initial stats."""
        with self.get_conn() as conn:
            # Insert torrent metadata
            conn.execute(
                """
                INSERT OR IGNORE INTO torrents (
                    infohash, filename, pubdate, size_bytes, nyaa_id,
                    trusted, remake, guessit_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    torrent_data.infohash,
                    torrent_data.filename,
                    torrent_data.pubdate,
                    torrent_data.size_bytes,
                    torrent_data.nyaa_id,
                    torrent_data.trusted,
                    torrent_data.remake,
                    json.dumps(torrent_data.guessit_data)
                    if torrent_data.guessit_data
                    else None,
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
        self, infohash: str, stats: StatsData, timestamp: Instant | None = None
    ) -> None:
        """Insert statistics for a torrent."""
        if timestamp is None:
            timestamp = self.now_func().round()

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
