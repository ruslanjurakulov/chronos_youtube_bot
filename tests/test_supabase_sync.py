"""Tests for modules/supabase_sync.py.

No real network calls: `requests.post` is mocked. A real tempdir StateStore is
used so mirror_from_store exercises the real read path and row shaping.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.state_store import StateStore
from modules.supabase_sync import SupabaseSync


class SupabaseSyncDisabledTestCase(unittest.TestCase):
    def test_disabled_without_credentials(self):
        sync = SupabaseSync(url="", service_key="")
        self.assertFalse(sync.enabled)
        self.assertEqual(sync.upsert("videos", [{"video_id": "v1"}], on_conflict="video_id"), 0)

    def test_disabled_mirror_returns_empty(self):
        sync = SupabaseSync(url="", service_key="")
        self.assertEqual(sync.mirror_from_store(MagicMock()), {})


class SupabaseSyncEnabledTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_chronos.db"
        self.store = StateStore(self.db_path)
        self.sync = SupabaseSync(url="https://demo.supabase.co", service_key="service-key-123")

    def tearDown(self):
        self.store.close()
        self._tmpdir.cleanup()

    def _ok_response(self):
        resp = MagicMock()
        resp.status_code = 201
        resp.text = ""
        return resp

    def test_enabled_with_credentials(self):
        self.assertTrue(self.sync.enabled)

    def test_upsert_posts_with_conflict_and_auth(self):
        with patch("modules.supabase_sync.requests.post", return_value=self._ok_response()) as post:
            n = self.sync.upsert("videos", [{"video_id": "v1", "title": "T"}], on_conflict="video_id")
        self.assertEqual(n, 1)
        _, kwargs = post.call_args
        self.assertEqual(kwargs["params"]["on_conflict"], "video_id")
        self.assertIn("merge-duplicates", kwargs["headers"]["Prefer"])
        self.assertEqual(kwargs["headers"]["apikey"], "service-key-123")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer service-key-123")

    def test_upsert_empty_rows_is_noop(self):
        with patch("modules.supabase_sync.requests.post") as post:
            self.assertEqual(self.sync.upsert("videos", [], on_conflict="video_id"), 0)
        post.assert_not_called()

    def test_upsert_http_error_returns_zero(self):
        bad = MagicMock()
        bad.status_code = 400
        bad.text = "bad request"
        with patch("modules.supabase_sync.requests.post", return_value=bad):
            self.assertEqual(self.sync.upsert("videos", [{"video_id": "v1"}], on_conflict="video_id"), 0)

    def test_upsert_network_error_returns_zero(self):
        with patch("modules.supabase_sync.requests.post", side_effect=RuntimeError("connection reset")):
            self.assertEqual(self.sync.upsert("videos", [{"video_id": "v1"}], on_conflict="video_id"), 0)

    def test_mirror_from_store_covers_all_tables(self):
        # Seed one row into each mirrored table so every upsert has something.
        self.store.record_video(video_id="v1", topic="Rome", title="T", published_at="2026-08-20T00:00:00")
        self.store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-08-25", views=100)
        self.store.record_feedback_signal(video_id="v1", signal="HIGH_RETENTION", analyzed_date="2026-08-25", topic="Rome")
        self.store.upsert_topic_performance(topic="Rome", score=88.0, videos_analyzed=1, updated_at="2026-08-25")
        self.store.record_competitor_snapshot(
            video_id="cv1", channel_id="c1", title="rival", view_count=10, like_count=1,
            comment_count=0, published_at="2026-08-01", polled_date="2026-08-25", view_velocity=1.0,
        )
        self.store.record_trending_snapshot(
            video_id="tv1", title="trend", view_count=99, like_count=5, comment_count=2,
            published_at="2026-08-02", region_code="US", category_id="24", polled_date="2026-08-25",
        )
        from modules import event_log as events
        events.emit(events.TOPIC_SELECTED, agent="topic_manager", metadata={"topic": "Rome"}, store=self.store)

        posted_tables = []

        def capture(url, **kwargs):
            posted_tables.append(url.rsplit("/", 1)[-1])
            return self._ok_response()

        with patch("modules.supabase_sync.requests.post", side_effect=capture):
            counts = self.sync.mirror_from_store(self.store)

        # Every mirrored table got a POST and a non-zero count.
        for table in ("videos", "metrics_snapshots", "feedback_signals", "topic_performance",
                      "competitor_snapshots", "trending_snapshots", "system_events"):
            self.assertIn(table, posted_tables, f"{table} was not mirrored")
            self.assertEqual(counts.get(table), 1)

    def test_event_row_gets_synthetic_key_and_no_local_id(self):
        row = SupabaseSync._event_row({"id": 7, "ts": "2026-08-25T00:00:00", "event": "topic.selected", "video_id": "v1"})
        self.assertNotIn("id", row)
        self.assertEqual(row["event_key"], "2026-08-25T00:00:00|topic.selected|7")

    def test_strip_local_id(self):
        self.assertEqual(SupabaseSync._strip_local_id({"id": 3, "video_id": "v1"}), {"video_id": "v1"})


if __name__ == "__main__":
    unittest.main()
