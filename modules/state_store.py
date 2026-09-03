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

CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       TEXT NOT NULL,
    channel_id     TEXT NOT NULL,
    title          TEXT,
    view_count     INTEGER,
    like_count     INTEGER,
    comment_count  INTEGER,
    published_at   TEXT,
    polled_date    TEXT NOT NULL,
    view_velocity  REAL,
    UNIQUE (video_id, polled_date)
);

CREATE INDEX IF NOT EXISTS idx_competitor_channel_date
    ON competitor_snapshots (channel_id, polled_date);

CREATE TABLE IF NOT EXISTS trending_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       TEXT NOT NULL,
    title          TEXT,
    view_count     INTEGER,
    like_count     INTEGER,
    comment_count  INTEGER,
    published_at   TEXT,
    region_code    TEXT,
    category_id    TEXT,
    polled_date    TEXT NOT NULL,
    UNIQUE (video_id, polled_date, region_code)
);

CREATE INDEX IF NOT EXISTS idx_trending_date
    ON trending_snapshots (polled_date);

CREATE TABLE IF NOT EXISTS demand_signals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_phrase          TEXT NOT NULL,
    mention_count         INTEGER NOT NULL,
    example_comment_ids   TEXT,
    polled_date           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_demand_date
    ON demand_signals (polled_date);

CREATE TABLE IF NOT EXISTS feedback_signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id         TEXT NOT NULL,
    topic            TEXT,
    signal           TEXT NOT NULL,
    metric_value     REAL,
    channel_baseline REAL,
    detail           TEXT,
    analyzed_date    TEXT NOT NULL,
    UNIQUE (video_id, signal, analyzed_date)
);

CREATE INDEX IF NOT EXISTS idx_feedback_date
    ON feedback_signals (analyzed_date);

CREATE TABLE IF NOT EXISTS topic_performance (
    topic            TEXT PRIMARY KEY,
    score            REAL NOT NULL,
    videos_analyzed  INTEGER NOT NULL,
    avg_views_per_day REAL,
    reason           TEXT,
    updated_at       TEXT NOT NULL
);
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

    # -- competitor snapshots -------------------------------------------------

    def record_competitor_snapshot(
        self,
        video_id: str,
        channel_id: str,
        polled_date: str,
        title: str = "",
        view_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        published_at: str = "",
        view_velocity: float = 0.0,
    ):
        """Insert or replace a competitor video's snapshot for a given poll date.

        One row per (video_id, polled_date) — a re-poll for the same date
        overwrites rather than accumulating duplicates, same pattern as
        record_metrics_snapshot.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO competitor_snapshots
                    (video_id, channel_id, title, view_count, like_count,
                     comment_count, published_at, polled_date, view_velocity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, polled_date) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    title=excluded.title,
                    view_count=excluded.view_count,
                    like_count=excluded.like_count,
                    comment_count=excluded.comment_count,
                    published_at=excluded.published_at,
                    view_velocity=excluded.view_velocity
                """,
                (video_id, channel_id, title, view_count, like_count,
                 comment_count, published_at, polled_date, view_velocity),
            )

    def list_competitor_snapshots(
        self, channel_id: str | None = None, since: str | None = None, limit: int = 200
    ) -> list[dict]:
        """List competitor snapshots, most recently polled first.

        `channel_id` restricts to one channel; `since` (ISO date) restricts to
        snapshots polled on or after that date.
        """
        clauses, params = [], []
        if channel_id:
            clauses.append("channel_id = ?")
            params.append(channel_id)
        if since:
            clauses.append("polled_date >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM competitor_snapshots {where} ORDER BY polled_date DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- trending snapshots -----------------------------------------------------

    def record_trending_snapshot(
        self,
        video_id: str,
        polled_date: str,
        title: str = "",
        view_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        published_at: str = "",
        region_code: str = "",
        category_id: str = "",
    ):
        """Insert or replace a trending-video snapshot for a given poll date.

        One row per (video_id, polled_date, region_code) — the same video can
        legitimately trend in more than one region on the same day.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO trending_snapshots
                    (video_id, title, view_count, like_count, comment_count,
                     published_at, region_code, category_id, polled_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, polled_date, region_code) DO UPDATE SET
                    title=excluded.title,
                    view_count=excluded.view_count,
                    like_count=excluded.like_count,
                    comment_count=excluded.comment_count,
                    published_at=excluded.published_at,
                    category_id=excluded.category_id
                """,
                (video_id, title, view_count, like_count, comment_count,
                 published_at, region_code, category_id, polled_date),
            )

    def list_trending_snapshots(self, since: str | None = None, limit: int = 200) -> list[dict]:
        """List trending-video snapshots, most recently polled first."""
        if since:
            rows = self.conn.execute(
                "SELECT * FROM trending_snapshots WHERE polled_date >= ? "
                "ORDER BY polled_date DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM trending_snapshots ORDER BY polled_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- audience demand signals ------------------------------------------------

    def record_demand_signal(
        self,
        topic_phrase: str,
        mention_count: int,
        polled_date: str,
        example_comment_ids: str = "",
    ):
        """Append one audience-demand signal from a poll run.

        Unlike the snapshot tables above, this is a plain append log (no
        upsert) — each poll run's clustering can legitimately produce a
        different representative phrase for a similar underlying request,
        and collapsing that here would lose signal a downstream reader might
        want (e.g. trending phrasing over time).
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO demand_signals (topic_phrase, mention_count, example_comment_ids, polled_date)
                VALUES (?, ?, ?, ?)
                """,
                (topic_phrase, mention_count, example_comment_ids, polled_date),
            )

    def list_demand_signals(self, since: str | None = None, limit: int = 200) -> list[dict]:
        """List audience-demand signals, most recently polled first."""
        if since:
            rows = self.conn.execute(
                "SELECT * FROM demand_signals WHERE polled_date >= ? "
                "ORDER BY polled_date DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM demand_signals ORDER BY polled_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- feedback signals --------------------------------------------------

    def record_feedback_signal(
        self,
        video_id: str,
        signal: str,
        analyzed_date: str,
        topic: str = "",
        metric_value: float | None = None,
        channel_baseline: float | None = None,
        detail: str = "",
    ):
        """Record a discrete learning signal for a video on a given analysis date.

        One row per (video_id, signal, analyzed_date) — re-running the feedback
        analysis on the same day overwrites rather than accumulating duplicates,
        so the signal history reflects one verdict per video per analysis run.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO feedback_signals
                    (video_id, topic, signal, metric_value, channel_baseline, detail, analyzed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, signal, analyzed_date) DO UPDATE SET
                    topic=excluded.topic,
                    metric_value=excluded.metric_value,
                    channel_baseline=excluded.channel_baseline,
                    detail=excluded.detail
                """,
                (video_id, topic, signal, metric_value, channel_baseline, detail, analyzed_date),
            )

    def list_feedback_signals(self, since: str | None = None, limit: int = 200) -> list[dict]:
        """List feedback/learning signals, most recently analyzed first."""
        if since:
            rows = self.conn.execute(
                "SELECT * FROM feedback_signals WHERE analyzed_date >= ? "
                "ORDER BY analyzed_date DESC, id DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM feedback_signals ORDER BY analyzed_date DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- topic performance -------------------------------------------------

    def upsert_topic_performance(
        self,
        topic: str,
        score: float,
        videos_analyzed: int,
        updated_at: str,
        avg_views_per_day: float | None = None,
        reason: str = "",
    ):
        """Insert or update the learned performance score for a topic.

        One row per topic — the latest feedback analysis replaces the earlier
        score, keeping a single current verdict per topic that Topic Manager
        can read when choosing what to make next.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO topic_performance
                    (topic, score, videos_analyzed, avg_views_per_day, reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic) DO UPDATE SET
                    score=excluded.score,
                    videos_analyzed=excluded.videos_analyzed,
                    avg_views_per_day=excluded.avg_views_per_day,
                    reason=excluded.reason,
                    updated_at=excluded.updated_at
                """,
                (topic, score, videos_analyzed, avg_views_per_day, reason, updated_at),
            )

    def get_topic_performance(self, topic: str) -> dict | None:
        """Return the learned performance row for one topic, or None."""
        row = self.conn.execute(
            "SELECT * FROM topic_performance WHERE topic = ?", (topic,)
        ).fetchone()
        return dict(row) if row else None

    def list_topic_performance(self, limit: int = 200) -> list[dict]:
        """List learned topic-performance rows, highest score first."""
        rows = self.conn.execute(
            "SELECT * FROM topic_performance ORDER BY score DESC, videos_analyzed DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
