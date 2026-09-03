#!/usr/bin/env python3
"""Scheduled entry point for the intelligence layer — see
.github/workflows/intelligence_poll.yml.

Runs four independent passes, each defensive on its own: one bad video, one
bad API response, or one entire sub-system being down must never abort the
rest of the poll.

  1. IntelligencePoller.run_all() — own-channel analytics, competitor
     monitoring, and trending videos (see modules/intelligence_poller.py).
  2. Comment fetch + classify + demand aggregation for recently published
     videos (StateStore.list_videos() — never a hardcoded list).
  3. Feed TopicRecommender's resulting suggestions into ContentPlanner's
     queue — this is the producer side of the content-planning loop;
     modules/topic_manager.py is the consumer side (checks the queue
     before spending a Gemini call on a fresh topic).
  4. Run the feedback loop (modules/feedback_engine.py) over the freshly
     polled metrics — derive learning signals and per-topic scores that
     Topic Manager reads on the next video run. This is the step that closes
     the loop: published-video performance actually influences future topics.

This script does not decide *when* to run — that's the workflow's cron
schedule. It only does the work once invoked.
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/intelligence_poll.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("intelligence_poll")

from modules.audience_demand import AudienceDemandEngine
from modules.comment_fetcher import CommentFetcher
from modules.comment_intelligence import classify_comments
from modules.content_planner import ContentPlanner
from modules.feedback_engine import FeedbackEngine
from modules.intelligence_poller import IntelligencePoller
from modules.state_store import StateStore
from modules.topic_recommender import TopicRecommender


def _competitor_channel_ids() -> list[str]:
    raw = os.getenv("COMPETITOR_CHANNEL_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def poll_comments_for_recent_videos(store: StateStore, limit: int = 10) -> None:
    """Fetch and classify comments for the most recently published videos.

    A CommentFetcher auth failure (no token yet, expired credentials) skips
    this whole pass rather than crashing the poll — the analytics/competitor/
    trend pass above is independent and should still have run.
    """
    try:
        fetcher = CommentFetcher()
    except Exception as e:
        logger.warning("CommentFetcher auth failed (%s: %s) — skipping comment polling", type(e).__name__, e)
        return

    all_records = []
    for video in store.list_videos(limit=limit):
        video_id = video.get("video_id")
        if not video_id:
            continue
        try:
            comments = fetcher.fetch_comments(video_id)
            if not comments:
                continue
            classified = classify_comments(comments)
            flagged = [c for c in classified if c.flagged_injection_attempt]
            if flagged:
                logger.warning(
                    "Video %s: %d comment(s) flagged as possible prompt-injection attempts",
                    video_id, len(flagged),
                )
            text_by_id = {c["id"]: c["text"] for c in comments}
            all_records.extend(
                {
                    "comment_id": c.comment_id,
                    "sentiment": c.sentiment,
                    "category": c.category,
                    "text": text_by_id.get(c.comment_id, ""),
                }
                for c in classified
            )
            logger.info("Video %s: %d comment(s) classified", video_id, len(classified))
        except Exception as e:
            logger.warning("Comment poll failed for video %s (%s: %s) — skipping", video_id, type(e).__name__, e)
            continue

    if not all_records:
        return
    signals = AudienceDemandEngine().analyze(all_records)
    if not signals:
        return

    top = [(s.topic_phrase, s.mention_count) for s in signals[:5]]
    logger.info("Audience demand — top requested topics: %s", top)

    polled_date = date.today().isoformat()
    written = 0
    for signal in signals:
        try:
            store.record_demand_signal(
                topic_phrase=signal.topic_phrase,
                mention_count=signal.mention_count,
                polled_date=polled_date,
                example_comment_ids=",".join(str(i) for i in signal.example_comment_ids),
            )
            written += 1
        except Exception as e:
            logger.warning("Failed to persist demand signal %r (%s: %s) — skipping", signal.topic_phrase, type(e).__name__, e)
    logger.info("Persisted %d/%d demand signal(s)", written, len(signals))


def enqueue_topic_suggestions(limit: int = 5) -> int:
    """Feeds TopicRecommender's ranked suggestions into ContentPlanner's
    queue, so a future pick_topic() call can consume one directly instead
    of spending a Gemini call. Runs after the analytics/competitor/trend
    and comment/demand passes above so it sees the freshest persisted data.

    Never raises: TopicRecommender().suggest_topics() already degrades to
    [] on any internal failure, and ContentPlanner's own dedup means
    re-running this poll repeatedly against an unchanged database just
    reuses existing queued entries rather than growing the queue unbounded.
    """
    try:
        opportunities = TopicRecommender().suggest_topics(limit=limit)
    except Exception as e:
        logger.warning("TopicRecommender failed (%s: %s) — nothing enqueued this run", type(e).__name__, e)
        return 0
    if not opportunities:
        return 0

    try:
        planner = ContentPlanner()
    except Exception as e:
        logger.warning("Failed to construct ContentPlanner (%s: %s) — nothing enqueued this run", type(e).__name__, e)
        return 0

    enqueued = 0
    for opp in opportunities:
        try:
            planner.enqueue_opportunity(opp)
            enqueued += 1
        except Exception as e:
            logger.warning("Failed to enqueue suggestion %r (%s: %s) — skipping", opp.topic, type(e).__name__, e)
    logger.info("Content planner: %d/%d suggestion(s) enqueued (existing queued duplicates are reused, not duplicated)", enqueued, len(opportunities))
    return enqueued


def run_feedback_analysis() -> dict:
    """Run the feedback loop over the metrics this poll (and prior polls) have
    persisted: derive learning signals + per-topic scores that Topic Manager
    reads on the next video run. Runs last, after own-channel metrics have been
    freshly polled above. Never raises (FeedbackEngine is defensive)."""
    try:
        summary = FeedbackEngine().run()
    except Exception as e:
        logger.warning("Feedback loop failed (%s: %s) — no scores updated this run", type(e).__name__, e)
        return {"videos_analyzed": 0, "signals_recorded": 0, "topics_scored": 0}
    logger.info("Feedback loop summary: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Chronos intelligence poll")
    parser.add_argument("--skip-comments", action="store_true", help="Skip the comment fetch/classify pass")
    parser.add_argument("--skip-planning", action="store_true", help="Skip feeding suggestions into the content planner queue")
    parser.add_argument("--skip-feedback", action="store_true", help="Skip the feedback-loop scoring pass")
    args = parser.parse_args()

    logger.info("=== Intelligence poll starting ===")

    try:
        summary = IntelligencePoller().run_all(competitor_channel_ids=_competitor_channel_ids())
        logger.info("Analytics/competitor/trend summary: %s", summary)
    except Exception as e:
        # IntelligencePoller() eagerly authenticates AnalyticsClient at
        # construction time — an auth failure there must not take down the
        # independent comment-polling pass below.
        logger.warning(
            "IntelligencePoller failed (%s: %s) — analytics/competitor/trend pass skipped for this run",
            type(e).__name__, e,
        )

    if not args.skip_comments:
        with StateStore() as store:
            poll_comments_for_recent_videos(store)
    else:
        logger.info("Comment polling skipped (--skip-comments)")

    if not args.skip_planning:
        enqueue_topic_suggestions()
    else:
        logger.info("Content planning skipped (--skip-planning)")

    if not args.skip_feedback:
        run_feedback_analysis()
    else:
        logger.info("Feedback scoring skipped (--skip-feedback)")

    logger.info("=== Intelligence poll done ===")


if __name__ == "__main__":
    main()
