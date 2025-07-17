import logging
from collections.abc import Callable
from typing import Any

from whenever import Instant

from .database import Database

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        db: Database,
        batch_size: int = 40,
        now_func: Callable[[], Instant] = Instant.now,
    ):
        self.db = db
        self.batch_size = batch_size
        self.now_func = now_func

    def get_due_torrents(self) -> list[str]:
        """Get torrents that are due for scraping based on time-decay algorithm."""
        return self.get_due_torrents_with_window(0)

    def get_due_torrents_with_window(self, window_minutes: int) -> list[str]:
        """Get torrents that are due for scraping within a time window for batching."""
        now = self.now_func()
        now_julian = now.timestamp() / 86400.0 + 2440587.5  # Convert to julian day
        window_days = window_minutes / (24 * 60)  # Convert minutes to days

        with self.db.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT t.infohash
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                WHERE t.status = 'active'
                  AND (
                    s.last_scrape IS NULL
                    OR
                    CASE
                      WHEN (:now - julianday(t.pubdate)) <= 2 THEN
                        (:now - julianday(s.last_scrape) + :window) * 24 >= 1
                      WHEN (:now - julianday(t.pubdate)) <= 7 THEN
                        (:now - julianday(s.last_scrape) + :window) * 24 >= 4
                      WHEN (:now - julianday(t.pubdate)) <= 30 THEN
                        (:now - julianday(s.last_scrape) + :window) >= 1
                      WHEN (:now - julianday(t.pubdate)) <= 180 THEN
                        (:now - julianday(s.last_scrape) + :window) >= 7
                      ELSE
                        FALSE
                    END
                  )
                ORDER BY s.last_scrape ASC NULLS FIRST
                """,
                {
                    "now": now_julian,
                    "window": window_days,
                },
            )

            return [row["infohash"] for row in cursor.fetchall()]

    def get_metrics(self) -> dict[str, int]:
        """Get current system metrics."""
        now = self.now_func()
        now_julian = now.timestamp() / 86400.0 + 2440587.5  # Convert to julian day

        with self.db.get_conn() as conn:
            metrics = {}

            # Total torrents
            cursor = conn.execute("SELECT COUNT(*) as count FROM torrents")
            metrics["torrents_total"] = cursor.fetchone()["count"]

            # Active torrents
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM torrents WHERE status = 'active'"
            )
            metrics["torrents_active"] = cursor.fetchone()["count"]

            # Dead torrents
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM torrents WHERE status = 'dead'"
            )
            metrics["torrents_dead"] = cursor.fetchone()["count"]

            # Guessit failed torrents
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM torrents WHERE status = 'guessit_failed'"
            )
            metrics["torrents_guessit_failed"] = cursor.fetchone()["count"]

            # Queue depth (torrents due for scraping)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                WHERE t.status = 'active'
                  AND (
                    s.last_scrape IS NULL
                    OR
                    CASE
                      WHEN (:now - julianday(t.pubdate)) <= 2 THEN
                        (:now - julianday(s.last_scrape)) * 24 >= 1
                      WHEN (:now - julianday(t.pubdate)) <= 7 THEN
                        (:now - julianday(s.last_scrape)) * 24 >= 4
                      WHEN (:now - julianday(t.pubdate)) <= 30 THEN
                        (:now - julianday(s.last_scrape)) >= 1
                      WHEN (:now - julianday(t.pubdate)) <= 180 THEN
                        (:now - julianday(s.last_scrape)) >= 7
                      ELSE
                        FALSE
                    END
                  )
                """,
                {"now": now_julian},
            )
            metrics["queue_depth"] = cursor.fetchone()["count"]

            # Total stats entries
            cursor = conn.execute("SELECT COUNT(*) as count FROM stats")
            metrics["stats_total"] = cursor.fetchone()["count"]

            # Recent stats (last 24 hours)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count FROM stats
                WHERE :now - julianday(timestamp) <= 1
                """,
                {"now": now_julian},
            )
            metrics["stats_recent"] = cursor.fetchone()["count"]

            return metrics

    def get_torrent_scrape_schedule(self, infohash: str) -> dict[str, Any] | None:
        """Get scrape schedule information for a specific torrent."""
        now = self.now_func()
        now_julian = now.timestamp() / 86400.0 + 2440587.5  # Convert to julian day

        with self.db.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT
                    t.infohash,
                    t.pubdate,
                    t.status,
                    s.last_scrape,
                    :now - julianday(t.pubdate) as age_days,
                    CASE
                        WHEN s.last_scrape IS NULL THEN 'never_scraped'
                        WHEN (:now - julianday(t.pubdate)) <= 2 THEN 'hourly'
                        WHEN (:now - julianday(t.pubdate)) <= 7 THEN 'every_4_hours'
                        WHEN (:now - julianday(t.pubdate)) <= 30 THEN 'daily'
                        WHEN (:now - julianday(t.pubdate)) <= 180 THEN 'weekly'
                        ELSE 'never'
                    END as schedule_type,
                    CASE
                        WHEN s.last_scrape IS NULL THEN 1
                        WHEN (:now - julianday(t.pubdate)) <= 2 THEN
                            (:now - julianday(s.last_scrape)) * 24 >= 1
                        WHEN (:now - julianday(t.pubdate)) <= 7 THEN
                            (:now - julianday(s.last_scrape)) * 24 >= 4
                        WHEN (:now - julianday(t.pubdate)) <= 30 THEN
                            (:now - julianday(s.last_scrape)) >= 1
                        WHEN (:now - julianday(t.pubdate)) <= 180 THEN
                            (:now - julianday(s.last_scrape)) >= 7
                        ELSE
                            0
                    END as is_due
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                WHERE t.infohash = :infohash
                """,
                {"now": now_julian, "infohash": infohash},
            )

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_schedule_summary(self) -> dict[str, int]:
        """Get summary of torrents by schedule type."""
        now = self.now_func()
        now_julian = now.timestamp() / 86400.0 + 2440587.5  # Convert to julian day

        with self.db.get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT
                    CASE
                        WHEN t.status != 'active' THEN t.status
                        WHEN s.last_scrape IS NULL THEN 'never_scraped'
                        WHEN (:now - julianday(t.pubdate)) <= 2 THEN 'hourly'
                        WHEN (:now - julianday(t.pubdate)) <= 7 THEN 'every_4_hours'
                        WHEN (:now - julianday(t.pubdate)) <= 30 THEN 'daily'
                        WHEN (:now - julianday(t.pubdate)) <= 180 THEN 'weekly'
                        ELSE 'never'
                    END as schedule_type,
                    COUNT(*) as count
                FROM torrents t
                LEFT JOIN (
                    SELECT infohash, MAX(timestamp) as last_scrape
                    FROM stats
                    GROUP BY infohash
                ) s ON t.infohash = s.infohash
                GROUP BY schedule_type
                """,
                {"now": now_julian},
            )

            return {row["schedule_type"]: row["count"] for row in cursor.fetchall()}
