"""Stage 1: Topic & History Manager — tracks used topics, picks fresh ones via Gemini."""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import GEMINI_MODEL, TOPIC_HISTORY_FILE, SCRIPT_LANGUAGE
from modules.content_planner import ContentPlanner
from modules.gemini_client import generate_with_retry, make_client
from modules.originality_engine import OriginalityEngine
from modules.performance_analyzer import PerformanceAnalyzer
from modules.topic_recommender import TopicRecommender

logger = logging.getLogger(__name__)

MAX_TOPIC_ATTEMPTS = 3


class TopicManager:
    def __init__(self):
        TOPIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()
        self.client = make_client()
        self.originality = OriginalityEngine()
        self.recommender = self._safe_make_recommender()
        self.content_planner = self._safe_make_content_planner()
        self.performance_analyzer = self._safe_make_performance_analyzer()

    def _safe_make_recommender(self) -> TopicRecommender | None:
        """TopicRecommender degrades gracefully on its own (empty DB, a
        broken store, etc. all return "" rather than raising), but its
        constructor is not exercised by that guarantee — so failing to
        construct it at all must not stop topic selection from working.
        """
        try:
            return TopicRecommender()
        except Exception as e:
            logger.warning(
                "Failed to construct TopicRecommender (%s: %s) — proceeding without "
                "trend/demand suggestions in the topic prompt",
                type(e).__name__, e,
            )
            return None

    def _safe_make_content_planner(self) -> ContentPlanner | None:
        try:
            return ContentPlanner()
        except Exception as e:
            logger.warning(
                "Failed to construct ContentPlanner (%s: %s) — proceeding without "
                "the queued-topic check",
                type(e).__name__, e,
            )
            return None

    def _safe_make_performance_analyzer(self) -> PerformanceAnalyzer | None:
        """Same rationale as _safe_make_recommender: PerformanceAnalyzer's own
        methods already degrade to "" / [] on internal failure, but a
        construction failure isn't covered by that guarantee.
        """
        try:
            return PerformanceAnalyzer()
        except Exception as e:
            logger.warning(
                "Failed to construct PerformanceAnalyzer (%s: %s) — proceeding without "
                "past-performance context in the topic prompt",
                type(e).__name__, e,
            )
            return None

    def _load(self) -> dict:
        if TOPIC_HISTORY_FILE.exists():
            return json.loads(TOPIC_HISTORY_FILE.read_text())
        return {"used_topics": [], "sessions": []}

    def _save(self):
        TOPIC_HISTORY_FILE.write_text(json.dumps(self.history, indent=2, ensure_ascii=False))

    def _used_topics_str(self) -> str:
        topics = self.history["used_topics"]
        return "\n".join(f"- {t}" for t in topics[-80:]) if topics else "None yet."

    def _safe_originality_check(self, candidate: str):
        """OriginalityEngine's default embedder downloads model2vec weights from
        HuggingFace on first use — a transient network failure there must not
        crash topic selection (and with it the whole run). Returns None on
        failure, meaning "skip the check for this topic" rather than blocking.
        """
        try:
            return self.originality.check(candidate)
        except Exception as e:
            logger.warning(
                "OriginalityEngine.check failed (%s: %s) — skipping originality check for '%s'",
                type(e).__name__, e, candidate,
            )
            return None

    def _safe_originality_register(self, topic: str):
        try:
            self.originality.register(topic)
        except Exception as e:
            logger.warning(
                "OriginalityEngine.register failed (%s: %s) — '%s' still recorded in used_topics, "
                "just not in the originality vector store",
                type(e).__name__, e, topic,
            )

    def _generate_topic(self, niche: str) -> str:
        prompt = (
            f"You create viral YouTube Shorts scripts in the niche: '{niche}'.\n"
            f"Language: {SCRIPT_LANGUAGE}\n\n"
            f"Already used topics (DO NOT repeat these):\n{self._used_topics_str()}\n\n"
            "Pick ONE brand-new, highly engaging topic for a 5-minute YouTube video. "
            "Return ONLY the topic title — no explanation, no numbering."
        )
        # This is the feedback loop: real persisted trend/competitor/demand
        # data (when any exists — see TopicRecommender) offered as optional
        # inspiration, never as a directive. Gemini still makes the actual
        # call; this only gives it more to work with.
        if self.recommender is not None:
            suggestions = self.recommender.suggest_topics_as_prompt_text()
            if suggestions:
                prompt += f"\n\n{suggestions}"
        # Same feedback-loop spirit as the recommender block above, but for
        # what actually happened after publishing rather than what's
        # currently trending: real past-performance numbers, offered as
        # context, never as a directive (see PerformanceAnalyzer's own
        # "Honesty-preserving framing" docstring section).
        if self.performance_analyzer is not None:
            performance_context = self.performance_analyzer.analyze_videos_as_prompt_text()
            if performance_context:
                prompt += f"\n\n{performance_context}"
        response = generate_with_retry(self.client, GEMINI_MODEL, prompt)
        return response.text.strip().strip('"').strip("'")

    def _try_queued_topic(self) -> str | None:
        """Check modules/content_planner.py's queue before spending a Gemini
        call on a fresh topic. A queued entry (enqueued elsewhere — e.g. from
        TopicRecommender suggestions fed in by the intelligence poller) still
        goes through the same OriginalityEngine check as a Gemini-generated
        candidate would: real duplicate topics don't get a pass just because
        they came from the queue.

        A queued entry that's accepted is marked "published" in the planner
        immediately (optimistic — this happens at *pick* time, not at actual
        upload success). This is a deliberate simplification: threading the
        entry id through the rest of main.py's run just to mark it at the
        real moment of publish would be a much larger, more invasive change
        for a queue of non-scarce suggestions — if a run fails downstream,
        the same topic can simply be re-suggested or re-enqueued later.
        A hard-blocked duplicate is marked "skipped" (not left queued
        forever) and topic selection falls through to Gemini generation.

        Returns None (falls through to Gemini generation) if the planner is
        unavailable, the queue is empty, or the queued topic is hard-blocked.
        """
        if self.content_planner is None:
            return None

        entry = self.content_planner.next_topic()
        if entry is None:
            return None

        result = self._safe_originality_check(entry.topic)
        if result is not None and result.is_duplicate:
            logger.warning(
                "Queued topic '%s' (entry %s) hard-blocked as duplicate of '%s' — skipping it, falling back to Gemini",
                entry.topic, entry.entry_id, result.closest_match,
            )
            self.content_planner.mark_skipped(entry.entry_id, reason="hard-blocked as duplicate by originality check")
            return None

        if result is not None and result.needs_review:
            logger.warning(
                "Queued topic '%s' flagged for review as near-duplicate of '%s' — using anyway",
                entry.topic, result.closest_match,
            )

        self.content_planner.mark_published(entry.entry_id)
        logger.info("Using queued topic from content planner: '%s' (source=%s)", entry.topic, entry.source)
        return entry.topic

    def pick_topic(self, niche: str = "history mysteries") -> str:
        """Pick a topic for the next video.

        Checks modules/content_planner.py's queue first (see
        _try_queued_topic) — a queued suggestion, once it clears the same
        originality check a fresh one would, is used directly and no Gemini
        call is spent picking a topic at all. Only when the queue is empty
        or its candidate is rejected does this fall through to asking
        Gemini for a fresh one.

        The exact-string exclusion list handles topics Gemini has already
        seen; OriginalityEngine additionally catches paraphrased/reworded
        repeats that string matching misses. A hard-blocked duplicate is
        regenerated (bounded retries) rather than silently accepted; a
        flagged-for-review near-duplicate is logged but still used, since
        the threshold is a starting point, not a validated cutoff.
        """
        queued_topic = self._try_queued_topic()
        if queued_topic is not None:
            logger.info("Selected topic: %s", queued_topic)
            return queued_topic

        topic = None
        for attempt in range(1, MAX_TOPIC_ATTEMPTS + 1):
            candidate = self._generate_topic(niche)
            result = self._safe_originality_check(candidate)
            if result is None:
                topic = candidate
                break
            if result.is_duplicate:
                logger.warning(
                    "Topic '%s' hard-blocked as duplicate of '%s' (semantic=%.2f, lexical=%.2f), attempt %d/%d",
                    candidate, result.closest_match, result.semantic_score, result.lexical_score,
                    attempt, MAX_TOPIC_ATTEMPTS,
                )
                continue
            if result.needs_review:
                logger.warning(
                    "Topic '%s' flagged for review as near-duplicate of '%s' (semantic=%.2f, lexical=%.2f) — using anyway",
                    candidate, result.closest_match, result.semantic_score, result.lexical_score,
                )
            topic = candidate
            break

        if topic is None:
            logger.warning("All %d topic attempts hard-blocked as duplicates; using the last one anyway", MAX_TOPIC_ATTEMPTS)
            topic = candidate

        logger.info("Selected topic: %s", topic)
        return topic

    def register_topic(
        self,
        topic: str,
        video_path: str = "",
        video_id: str | None = None,
        video_url: str | None = None,
    ):
        """Mark topic as used after successful video creation."""
        self.history["used_topics"].append(topic)
        self.history["sessions"].append({
            "topic": topic,
            "date": datetime.utcnow().isoformat(),
            "video": str(video_path),
            "video_id": video_id,
            "video_url": video_url,
        })
        self._save()
        self._safe_originality_register(topic)
        logger.info("Topic registered: %s (video_id=%s)", topic, video_id)
