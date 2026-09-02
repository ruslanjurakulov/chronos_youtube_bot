"""Stage 1: Topic & History Manager — tracks used topics, picks fresh ones via Gemini."""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import GEMINI_MODEL, TOPIC_HISTORY_FILE, SCRIPT_LANGUAGE
from modules.gemini_client import generate_with_retry, make_client
from modules.originality_engine import OriginalityEngine
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
        response = generate_with_retry(self.client, GEMINI_MODEL, prompt)
        return response.text.strip().strip('"').strip("'")

    def pick_topic(self, niche: str = "history mysteries") -> str:
        """Ask Gemini for a fresh, viral topic not in history.

        The exact-string exclusion list handles topics Gemini has already
        seen; OriginalityEngine additionally catches paraphrased/reworded
        repeats that string matching misses. A hard-blocked duplicate is
        regenerated (bounded retries) rather than silently accepted; a
        flagged-for-review near-duplicate is logged but still used, since
        the threshold is a starting point, not a validated cutoff.
        """
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
