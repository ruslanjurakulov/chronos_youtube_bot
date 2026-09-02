"""Stage 1: Topic & History Manager — tracks used topics, picks fresh ones via Gemini."""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import GEMINI_MODEL, TOPIC_HISTORY_FILE, SCRIPT_LANGUAGE
from modules.gemini_client import generate_with_retry, make_client

logger = logging.getLogger(__name__)


class TopicManager:
    def __init__(self):
        TOPIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.history = self._load()
        self.client = make_client()

    def _load(self) -> dict:
        if TOPIC_HISTORY_FILE.exists():
            return json.loads(TOPIC_HISTORY_FILE.read_text())
        return {"used_topics": [], "sessions": []}

    def _save(self):
        TOPIC_HISTORY_FILE.write_text(json.dumps(self.history, indent=2, ensure_ascii=False))

    def _used_topics_str(self) -> str:
        topics = self.history["used_topics"]
        return "\n".join(f"- {t}" for t in topics[-80:]) if topics else "None yet."

    def pick_topic(self, niche: str = "history mysteries") -> str:
        """Ask Gemini for a fresh, viral topic not in history."""
        prompt = (
            f"You create viral YouTube Shorts scripts in the niche: '{niche}'.\n"
            f"Language: {SCRIPT_LANGUAGE}\n\n"
            f"Already used topics (DO NOT repeat these):\n{self._used_topics_str()}\n\n"
            "Pick ONE brand-new, highly engaging topic for a 5-minute YouTube video. "
            "Return ONLY the topic title — no explanation, no numbering."
        )
        response = generate_with_retry(self.client, GEMINI_MODEL, prompt)
        topic = response.text.strip().strip('"').strip("'")
        logger.info("Selected topic: %s", topic)
        return topic

    def register_topic(self, topic: str, video_path: str = ""):
        """Mark topic as used after successful video creation."""
        self.history["used_topics"].append(topic)
        self.history["sessions"].append({
            "topic": topic,
            "date": datetime.utcnow().isoformat(),
            "video": str(video_path),
        })
        self._save()
        logger.info("Topic registered: %s", topic)
