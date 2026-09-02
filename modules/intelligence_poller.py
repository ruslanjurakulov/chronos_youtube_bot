"""Intelligence poller — the scheduler-agnostic entry point that actually
runs the previously-standalone intelligence modules and persists what they
find.

Context
-------
`modules/analytics_client.py` (AnalyticsClient), `modules/competitor_monitor.py`
(CompetitorMonitor), `modules/trend_detector.py` (TrendDetector), and
`modules/state_store.py` (StateStore) all already exist and work, but nothing
in the pipeline calls any of them on a schedule. This module is that missing
piece: `IntelligencePoller.run_all()` is the single function a future
scheduled job (cron, a GitHub Actions workflow, whatever the repo owner
prefers) would call. Building that actual schedule/workflow is a deliberate
follow-up decision, NOT made here — see the module docstring note in the PR
this ships with.

Design: defensive per-sub-call, not defensive per-poll
-------------------------------------------------------
This poller exists to run unattended. A single bad response — a quota
error, a not-found video, a transient network blip, a video too new to have
analytics data yet — must never take down the rest of a run. So every
sub-call (each per-video analytics lookup, the competitor poll, the trend
poll) is wrapped in its own try/except that logs a warning and degrades to
an empty/zero result for just that piece, rather than letting the exception
propagate and abort everything else `run_all()` would otherwise have done.

Dependency injection
---------------------
Mirrors the pattern already used in `modules/originality_engine.py`
(`OriginalityEngine.__init__(embedder=None)` lazily constructs the real,
network-touching default only when no fake is injected): each of
`analytics_client`, `competitor_monitor`, and `trend_detector` defaults to
constructing its real counterpart, but accepts an injected fake/mock so
tests never make live API calls.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


class IntelligencePoller:
    """Runs the analytics/competitor/trend intelligence modules and persists
    their results via StateStore. The single entry point future scheduled
    jobs should call is `run_all()`.
    """

    def __init__(
        self,
        state_store=None,
        analytics_client=None,
        competitor_monitor=None,
        trend_detector=None,
    ):
        if state_store is not None:
            self.state_store = state_store
        else:
            from modules.state_store import StateStore

            self.state_store = StateStore()

        if analytics_client is not None:
            self.analytics_client = analytics_client
        else:
            from modules.analytics_client import AnalyticsClient

            self.analytics_client = AnalyticsClient()

        if competitor_monitor is not None:
            self.competitor_monitor = competitor_monitor
        else:
            from modules.competitor_monitor import CompetitorMonitor

            self.competitor_monitor = CompetitorMonitor()

        if trend_detector is not None:
            self.trend_detector = trend_detector
        else:
            from modules.trend_detector import TrendDetector

            self.trend_detector = TrendDetector()

    # -- own-channel analytics -------------------------------------------

    def poll_own_channel_metrics(self, days: int = 1) -> int:
        """For each video this bot has uploaded (per `StateStore.list_videos`)
        published within the last `days` days, pull a small recent analytics
        window (yesterday through today) via `AnalyticsClient.video_performance`
        and persist it via `StateStore.record_metrics_snapshot`.

        `days` bounds which *videos* are considered (recently-published ones —
        older videos are far less likely to need frequent re-polling and this
        keeps a single run's API usage small), not the analytics window
        itself, which is always the fixed short "yesterday to today" range
        regardless of `days`.

        One video's analytics call failing (bad video ID, too new to have
        data yet, quota exceeded, ...) is logged as a warning and does not
        stop the remaining videos from being processed. Returns the number
        of snapshots successfully written.
        """
        since = None
        if days is not None:
            since = (datetime.now().date() - timedelta(days=days)).isoformat()

        try:
            videos = self.state_store.list_videos(since=since) if since else self.state_store.list_videos()
        except Exception:
            logger.exception("Failed to list videos from state store; polling zero own-channel metrics")
            return 0

        today = date.today()
        start_date = (today - timedelta(days=1)).isoformat()
        end_date = today.isoformat()
        snapshot_date = end_date

        written = 0
        for video in videos:
            video_id = video.get("video_id")
            if not video_id:
                continue
            try:
                metrics = self.analytics_client.video_performance(video_id, start_date, end_date)
                self.state_store.record_metrics_snapshot(
                    video_id=video_id,
                    snapshot_date=snapshot_date,
                    views=int(metrics.get("views", 0) or 0),
                    likes=int(metrics.get("likes", 0) or 0),
                    comment_count=int(metrics.get("comments", 0) or 0),
                    watch_time_minutes=float(metrics.get("estimatedMinutesWatched", 0.0) or 0.0),
                    average_view_duration_seconds=float(metrics.get("averageViewDuration", 0.0) or 0.0),
                )
                written += 1
            except Exception:
                logger.warning(
                    "Failed to poll/record analytics for video_id=%s; skipping", video_id, exc_info=True
                )
                continue

        return written

    # -- competitors --------------------------------------------------------

    def poll_competitors(self, channel_ids: list) -> dict:
        """Thin entry point around `CompetitorMonitor.poll`. Returns whatever
        it gets back; on any failure, logs a warning and returns `{}` rather
        than raising.
        """
        try:
            return self.competitor_monitor.poll(channel_ids)
        except Exception:
            logger.warning("Competitor poll failed; returning empty result", exc_info=True)
            return {}

    # -- trends ---------------------------------------------------------

    def poll_trends(self, region_code: str = "US", category_id=None) -> list:
        """Thin entry point around `TrendDetector.trending`. Returns whatever
        it gets back; on any failure, logs a warning and returns `[]` rather
        than raising.
        """
        try:
            return self.trend_detector.trending(region_code=region_code, category_id=category_id)
        except Exception:
            logger.warning("Trend poll failed; returning empty result", exc_info=True)
            return []

    # -- orchestration --------------------------------------------------

    def run_all(self, competitor_channel_ids: list | None = None) -> dict:
        """Runs all three polls and returns a small summary dict. This is
        the single function a future scheduled job (cron, GitHub Action, or
        otherwise) would call; wiring it into an actual schedule is a
        deliberate follow-up decision not made by this module.
        """
        own_metrics_written = self.poll_own_channel_metrics()

        channel_ids = competitor_channel_ids or []
        competitor_results = self.poll_competitors(channel_ids) if channel_ids else {}

        trending_videos = self.poll_trends()

        return {
            "own_metrics_written": own_metrics_written,
            "competitor_channels_polled": len(competitor_results),
            "trending_videos_found": len(trending_videos),
        }
