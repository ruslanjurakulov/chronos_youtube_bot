"""Stage 8: State Store — persists video records and metrics snapshots in SQLite."""

import logging
import os
import sqlite3
from pathlib import Path

from config import HISTORY_DIR

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = HISTORY_DIR / "chronos.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id     TEXT PRIMARY KEY,
    topic        TEXT,
    title        TEXT,
    slug         TEXT,
    published_at TEXT,
    privacy      TEXT,
    category_id  TEXT,
    local_path   TEXT
);

CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id                             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id                       TEXT NOT NULL,
    snapshot_date                  TEXT NOT NULL,
    views                          INTEGER,
    likes                          INTEGER,
    comment_count                  INTEGER,
    watch_time_minutes             REAL,
    average_view_duration_seconds  REAL,
    FOREIGN KEY (video_id) REFERENCES videos (video_id),
    UNIQUE (video_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_metrics_video_date
    ON metrics_snapshots (video_id, snapshot_date);
"""


def _resolve_db_path() -> Path:
    """DB path is overridable via CHRONOS_STATE_DB, defaulting under HISTORY_DIR."""
    override = os.getenv("CHRONOS_STATE_DB")
    return Path(override) if override else DEFAULT_DB_PATH


class StateStore:
    """SQLite-backed persistence for uploaded videos and their metrics history.

    Used as a context manager, or opened/closed manually:

        with StateStore() as store:
            store.record_video(video_id="abc123", topic="...", ...)
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path is not None else _resolve_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.conn:
            self.conn.executescript(_SCHEMA)
        logger.info("State store ready at %s", self.db_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.conn.close()

    # -- videos ------------------------------------------------------------

    def record_video(
        self,
        video_id: str,
        topic: str = "",
        title: str = "",
        slug: str = "",
        published_at: str = "",
        privacy: str = "",
        category_id: str = "",
        local_path: str = "",
    ):
        """Insert a video row, or overwrite it if video_id already exists."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO videos
                    (video_id, topic, title, slug, published_at, privacy, category_id, local_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    topic=excluded.topic,
                    title=excluded.title,
                    slug=excluded.slug,
                    published_at=excluded.published_at,
                    privacy=excluded.privacy,
                    category_id=excluded.category_id,
                    local_path=excluded.local_path
                """,
                (video_id, topic, title, slug, published_at, privacy, category_id, local_path),
            )
        logger.info("Recorded video: %s (%s)", video_id, title or topic)

    def get_video(self, video_id: str) -> dict | None:
        """Return the video row as a dict, or None if it doesn't exist."""
        row = self.conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_videos(self, limit: int = 100, since: str | None = None) -> list[dict]:
        """List videos, most recently published first.

        `since` (ISO8601) restricts to videos published on or after that timestamp.
        """
        if since:
            rows = self.conn.execute(
                """
                SELECT * FROM videos
                WHERE published_at >= ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM videos ORDER BY published_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- metrics -------------------------------------------------------------

    def record_metrics_snapshot(
        self,
        video_id: str,
        snapshot_date: str,
        views: int = 0,
        likes: int = 0,
        comment_count: int = 0,
        watch_time_minutes: float = 0.0,
        average_view_duration_seconds: float = 0.0,
    ):
        """Insert or replace a metrics snapshot for a video on a given date.

        One row per (video_id, snapshot_date) — a re-poll for the same date
        overwrites the earlier snapshot rather than accumulating duplicates.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO metrics_snapshots
                    (video_id, snapshot_date, views, likes, comment_count,
                     watch_time_minutes, average_view_duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, snapshot_date) DO UPDATE SET
                    views=excluded.views,
                    likes=excluded.likes,
                    comment_count=excluded.comment_count,
                    watch_time_minutes=excluded.watch_time_minutes,
                    average_view_duration_seconds=excluded.average_view_duration_seconds
                """,
                (
                    video_id,
                    snapshot_date,
                    views,
                    likes,
                    comment_count,
                    watch_time_minutes,
                    average_view_duration_seconds,
                ),
            )
        logger.info("Recorded metrics snapshot: %s @ %s", video_id, snapshot_date)

    def latest_metrics(self, video_id: str) -> dict | None:
        """Return the most recent metrics snapshot for a video, or None."""
        row = self.conn.execute(
            """
            SELECT * FROM metrics_snapshots
            WHERE video_id = ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (video_id,),
        ).fetchone()
        return dict(row) if row else None

    def metrics_history(self, video_id: str) -> list[dict]:
        """Return all metrics snapshots for a video, ordered oldest to newest."""
        rows = self.conn.execute(
            """
            SELECT * FROM metrics_snapshots
            WHERE video_id = ?
            ORDER BY snapshot_date ASC
            """,
            (video_id,),
        ).fetchall()
        return [dict(row) for row in rows]
