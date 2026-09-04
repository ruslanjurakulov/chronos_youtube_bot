"""Supabase sync — mirror the local SQLite state into hosted Postgres so the
Command Center (a separate Next.js app on Vercel) can read real data.

Why this exists
---------------
The Python bot's state lives in `history/chronos.db`, which on the scheduled
GitHub Actions runners exists only for the life of one job (saved/restored via
`actions/cache`). Nothing outside CI can read it, so a hosted dashboard can't
show real data. This module mirrors the same rows into a Supabase Postgres
project; the Command Center then reads (and, via Supabase Realtime, live-
subscribes to) that hosted copy.

Configuration (both required to do anything):
  SUPABASE_URL          e.g. https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY  the service-role key (server-side only — never ship it
                        to the browser; the dashboard uses the anon key)

When either is unset the sync is DISABLED and every method is a no-op returning
0. That is the graceful default: the bot runs exactly as before, entirely
local, until you create a Supabase project and set the two secrets. Apply
`supabase/schema.sql` to the project once (see docs/SUPABASE.md) before enabling.

Guarantees
----------
Like event_log, this never raises into the pipeline: a Supabase outage, a bad
key, or a network error is logged and swallowed, and the local DB remains the
source of truth. Writes use PostgREST upserts (idempotent), so re-running a
sync against unchanged data is safe and produces no duplicates.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # seconds — a slow Supabase must not hang a scheduled job for long.

# Each mirrored table and the column(s) PostgREST upserts on. These conflict
# targets must match the UNIQUE/PRIMARY KEY constraints in supabase/schema.sql.
_UPSERT_TABLES = {
    "videos": "video_id",
    "metrics_snapshots": "video_id,snapshot_date",
    "feedback_signals": "video_id,signal,analyzed_date",
    "topic_performance": "topic",
    "competitor_snapshots": "video_id,polled_date",
    "trending_snapshots": "video_id,polled_date,region_code",
    "content_queue": "entry_id",
    "pipeline_runs": "run_id",
}


class SupabaseSync:
    def __init__(self, url: str | None = None, service_key: str | None = None):
        self.url = (url if url is not None else os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key if service_key is not None else os.getenv("SUPABASE_SERVICE_KEY", "")
        self.enabled = bool(self.url and self.service_key)
        if not self.enabled:
            logger.info(
                "SupabaseSync disabled (SUPABASE_URL / SUPABASE_SERVICE_KEY not set) — "
                "running local-only; nothing is mirrored to the Command Center"
            )

    # -- low-level ---------------------------------------------------------

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def upsert(self, table: str, rows: list[dict], on_conflict: str | None = None) -> int:
        """Upsert `rows` into `table` via PostgREST. Returns the number sent (0
        when disabled, empty, or on any failure). Never raises."""
        if not self.enabled or not rows:
            return 0
        params = {}
        prefer = "resolution=merge-duplicates,return=minimal"
        if on_conflict:
            params["on_conflict"] = on_conflict
        try:
            resp = requests.post(
                f"{self.url}/rest/v1/{table}",
                params=params,
                json=rows,
                headers=self._headers({"Prefer": prefer}),
                timeout=_TIMEOUT,
            )
            if resp.status_code >= 300:
                logger.warning("Supabase upsert into %s failed: HTTP %s %s", table, resp.status_code, resp.text[:300])
                return 0
            return len(rows)
        except Exception as e:
            logger.warning("Supabase upsert into %s errored (%s: %s)", table, type(e).__name__, e)
            return 0

    # -- high-level --------------------------------------------------------

    def mirror_from_store(self, store, events_limit: int = 500) -> dict:
        """Mirror the current local state into Supabase and return per-table
        counts. Reads through the given StateStore. Never raises.

        Stateful tables are upserted on their natural keys (idempotent).
        Append-only system_events are upserted on a synthetic `event_key` built
        from the local row id + timestamp, so re-syncing the same events does
        not create duplicates.
        """
        if not self.enabled:
            return {}

        counts: dict[str, int] = {}

        # -- stateful tables (natural-key upserts) --
        readers = {
            "videos": lambda: store.list_videos(limit=100000),
            "metrics_snapshots": None,  # no bulk lister; handled below
            "feedback_signals": lambda: store.list_feedback_signals(limit=100000),
            "topic_performance": lambda: store.list_topic_performance(limit=100000),
            "competitor_snapshots": lambda: store.list_competitor_snapshots(limit=100000),
            "trending_snapshots": lambda: store.list_trending_snapshots(limit=100000),
        }
        for table, reader in readers.items():
            if reader is None:
                continue
            try:
                rows = [self._strip_local_id(r) for r in reader()]
            except Exception as e:
                logger.warning("Failed reading %s for Supabase mirror (%s: %s)", table, type(e).__name__, e)
                continue
            counts[table] = self.upsert(table, rows, on_conflict=_UPSERT_TABLES[table])

        # -- metrics snapshots: gather per video (no bulk lister exists) --
        try:
            metrics_rows = self._gather_metrics(store)
            counts["metrics_snapshots"] = self.upsert(
                "metrics_snapshots", metrics_rows, on_conflict=_UPSERT_TABLES["metrics_snapshots"]
            )
        except Exception as e:
            logger.warning("Failed gathering metrics_snapshots for mirror (%s: %s)", type(e).__name__, e)

        # -- events (append-only, synthetic-key upsert) --
        try:
            events = store.list_events(limit=events_limit)
            event_rows = [self._event_row(e) for e in events]
            counts["system_events"] = self.upsert("system_events", event_rows, on_conflict="event_key")
        except Exception as e:
            logger.warning("Failed mirroring system_events (%s: %s)", type(e).__name__, e)

        logger.info("Supabase mirror complete: %s", counts)
        return counts

    def mirror_planner_and_runs(self, planner=None, machine=None) -> dict:
        """Mirror the two pieces of operational state the bot keeps on disk —
        ContentPlanner's queue and PipelineStateMachine's runs — into Supabase
        so the Command Center can see them.

        Purely additive observability: nothing reads these rows back into the
        pipeline, and the publish path is untouched. `human_approved` is
        mirrored as the audit-trail flag it already is; mirroring it does not
        gate anything.

        Constructs its own ContentPlanner / PipelineStateMachine when none is
        injected (tests inject fakes). Never raises — a failure here must not
        affect the poll that called it.
        """
        if not self.enabled:
            return {}

        counts: dict[str, int] = {}

        # -- content queue --
        try:
            if planner is None:
                from modules.content_planner import ContentPlanner

                planner = ContentPlanner()
            rows = [self._queue_row(e) for e in planner.list_entries()]
            counts["content_queue"] = self.upsert(
                "content_queue", rows, on_conflict=_UPSERT_TABLES["content_queue"]
            )
        except Exception as e:
            logger.warning("Failed mirroring content_queue (%s: %s)", type(e).__name__, e)

        # -- pipeline runs --
        try:
            if machine is None:
                from modules.pipeline_stages import PipelineStateMachine

                machine = PipelineStateMachine()
            rows = [self._run_row(r) for r in machine.list_runs()]
            counts["pipeline_runs"] = self.upsert(
                "pipeline_runs", rows, on_conflict=_UPSERT_TABLES["pipeline_runs"]
            )
        except Exception as e:
            logger.warning("Failed mirroring pipeline_runs (%s: %s)", type(e).__name__, e)

        logger.info("Supabase operational mirror complete: %s", counts)
        return counts

    @staticmethod
    def _queue_row(entry) -> dict:
        """One CalendarEntry as a content_queue row."""
        d = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
        return {
            "entry_id": d.get("entry_id"),
            "topic": d.get("topic"),
            "added_at": d.get("added_at"),
            "source": d.get("source") or None,
            "rationale": d.get("rationale") or None,
            "status": d.get("status") or "queued",
        }

    @staticmethod
    def _run_row(run) -> dict:
        """One PipelineRun as a pipeline_runs row. `started_at` / `updated_at`
        are the first and last real stage-transition timestamps, so the Command
        Center can order runs without inventing a clock."""
        d = run.to_dict() if hasattr(run, "to_dict") else dict(run)
        history = d.get("history") or []
        stamps = [t.get("timestamp") for t in history if isinstance(t, dict) and t.get("timestamp")]
        stamps.sort()
        return {
            "run_id": d.get("run_id"),
            "topic": d.get("topic"),
            "current_stage": d.get("current_stage"),
            "human_approved": bool(d.get("human_approved", False)),
            "approved_by": d.get("approved_by"),
            "approved_at": d.get("approved_at"),
            "history": history,
            "started_at": stamps[0] if stamps else None,
            "updated_at": stamps[-1] if stamps else None,
        }

    @staticmethod
    def _strip_local_id(row: dict) -> dict:
        """Drop the SQLite autoincrement `id` — Supabase rows are keyed on their
        natural columns, not the local rowid."""
        return {k: v for k, v in row.items() if k != "id"}

    @staticmethod
    def _event_row(row: dict) -> dict:
        out = {k: v for k, v in row.items() if k != "id"}
        out["event_key"] = f"{row.get('ts', '')}|{row.get('event', '')}|{row.get('id', '')}"
        return out

    def _gather_metrics(self, store) -> list[dict]:
        """Collect every video's latest metrics snapshot. StateStore exposes
        latest_metrics(video_id) rather than a bulk lister, so walk the videos.
        (Command Center charts read the full history from Supabase; this v1
        mirrors the latest snapshot per video, which is what the tiles need.)"""
        rows: list[dict] = []
        for video in store.list_videos(limit=100000):
            vid = video.get("video_id")
            if not vid:
                continue
            metrics = store.latest_metrics(vid)
            if metrics:
                rows.append(self._strip_local_id(metrics))
        return rows
