"""Tests for modules/topic_manager.py, focused on the content-planner queue
integration added alongside tools/run_intelligence_poll.py's producer side
(_try_queued_topic / pick_topic checking ContentPlanner before spending a
Gemini call).

OriginalityEngine and TopicRecommender are mocked out (their own behavior is
covered by tests/test_originality_engine.py and tests/test_topic_recommender.py
respectively) so these tests isolate the queue-check control flow itself.
ContentPlanner is real, tempdir-backed — its own dedup/lifecycle behavior is
already covered by tests/test_content_planner.py, but exercising the real
thing here proves the integration actually calls it correctly (real
mark_published/mark_skipped side effects, not just mock call assertions).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.content_planner import ContentPlanner
from modules.originality_engine import OriginalityResult


class TopicManagerQueueIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.history_path = Path(self._tmpdir.name) / "topics.json"
        self.calendar_path = Path(self._tmpdir.name) / "content_calendar.json"

        import config
        self._orig_history_file = config.TOPIC_HISTORY_FILE
        config.TOPIC_HISTORY_FILE = self.history_path

    def tearDown(self):
        import config
        config.TOPIC_HISTORY_FILE = self._orig_history_file
        self._tmpdir.cleanup()

    def _patch(self, target, **kwargs):
        """patch.object-style helper that keeps the patch alive for the rest
        of the test (via addCleanup) instead of only within a `with` block —
        pick_topic() is called after construction, outside any narrower
        `with patch(...)` a helper method could otherwise use, so the mocks
        for make_client/generate_with_retry etc. must still be active then.
        """
        patcher = patch(target, **kwargs)
        mock_obj = patcher.start()
        self.addCleanup(patcher.stop)
        return mock_obj

    def _make_manager(self, originality_check_result=None, gemini_text="A Freshly Generated Topic"):
        """Builds a TopicManager with make_client/generate_with_retry/
        OriginalityEngine mocked out (patches remain active for the rest of
        the test, including the pick_topic() call made after this returns),
        but a real tempdir-backed ContentPlanner and a mocked TopicRecommender
        forced to return no suggestions (prompt-text rendering isn't this
        file's concern — see tests/test_topic_recommender.py for that).
        """
        fake_originality = MagicMock()
        fake_originality.check.return_value = originality_check_result
        fake_originality.register.return_value = None

        fake_recommender = MagicMock()
        fake_recommender.suggest_topics_as_prompt_text.return_value = ""

        gen_mock = MagicMock()
        gen_mock.text = gemini_text

        self._patch("modules.topic_manager.make_client", return_value=MagicMock())
        self._patch("modules.topic_manager.generate_with_retry", return_value=gen_mock)
        self._patch("modules.topic_manager.OriginalityEngine", return_value=fake_originality)
        self._patch("modules.topic_manager.TopicRecommender", return_value=fake_recommender)
        self._patch("modules.topic_manager.ContentPlanner", side_effect=lambda: ContentPlanner(store_path=self.calendar_path))

        from modules.topic_manager import TopicManager
        return TopicManager()

    def test_empty_queue_falls_through_to_gemini(self):
        result = OriginalityResult(is_duplicate=False, needs_review=False, closest_match=None, semantic_score=0.0, lexical_score=0.0)
        tm = self._make_manager(originality_check_result=result, gemini_text="Gemini's Pick")

        topic = tm.pick_topic("history mysteries")

        self.assertEqual(topic, "Gemini's Pick")

    def test_queued_topic_is_used_without_a_gemini_call(self):
        planner = ContentPlanner(store_path=self.calendar_path)
        planner.enqueue("The Lost Colony of Roanoke", source="manual", rationale="test seed")

        result = OriginalityResult(is_duplicate=False, needs_review=False, closest_match=None, semantic_score=0.0, lexical_score=0.0)
        tm = self._make_manager(originality_check_result=result, gemini_text="SHOULD NOT BE USED")

        with patch("modules.topic_manager.generate_with_retry") as gen_mock:
            topic = tm.pick_topic("history mysteries")
            gen_mock.assert_not_called()

        self.assertEqual(topic, "The Lost Colony of Roanoke")

        entries = planner.list_entries()
        self.assertEqual(entries[0].status, "published")

    def test_queued_topic_hard_blocked_falls_back_to_gemini_and_marks_skipped(self):
        planner = ContentPlanner(store_path=self.calendar_path)
        entry = planner.enqueue("A Duplicate Topic", source="manual")

        blocked = OriginalityResult(is_duplicate=True, needs_review=False, closest_match="A Duplicate Topic (already used)", semantic_score=0.95, lexical_score=0.9)
        tm = self._make_manager(originality_check_result=blocked, gemini_text="Fresh Fallback Topic")

        topic = tm.pick_topic("history mysteries")

        self.assertEqual(topic, "Fresh Fallback Topic")
        entries = {e.entry_id: e for e in planner.list_entries()}
        self.assertEqual(entries[entry.entry_id].status, "skipped")

    def test_queued_topic_needs_review_is_used_anyway(self):
        planner = ContentPlanner(store_path=self.calendar_path)
        planner.enqueue("A Near-Duplicate Topic", source="manual")

        flagged = OriginalityResult(is_duplicate=False, needs_review=True, closest_match="Something Similar", semantic_score=0.82, lexical_score=0.7)
        tm = self._make_manager(originality_check_result=flagged, gemini_text="SHOULD NOT BE USED")

        topic = tm.pick_topic("history mysteries")

        self.assertEqual(topic, "A Near-Duplicate Topic")

    def test_content_planner_construction_failure_falls_back_to_gemini(self):
        fake_originality = MagicMock()
        fake_originality.check.return_value = OriginalityResult(is_duplicate=False, needs_review=False, closest_match=None, semantic_score=0.0, lexical_score=0.0)

        fake_recommender = MagicMock()
        fake_recommender.suggest_topics_as_prompt_text.return_value = ""

        gen_mock = MagicMock()
        gen_mock.text = "Gemini Fallback"

        with patch("modules.topic_manager.make_client", return_value=MagicMock()), \
             patch("modules.topic_manager.generate_with_retry", return_value=gen_mock), \
             patch("modules.topic_manager.OriginalityEngine", return_value=fake_originality), \
             patch("modules.topic_manager.TopicRecommender", return_value=fake_recommender), \
             patch("modules.topic_manager.ContentPlanner", side_effect=RuntimeError("disk full")):
            from modules.topic_manager import TopicManager
            tm = TopicManager()  # must not raise
            self.assertIsNone(tm.content_planner)
            topic = tm.pick_topic("history mysteries")

        self.assertEqual(topic, "Gemini Fallback")


if __name__ == "__main__":
    unittest.main()
