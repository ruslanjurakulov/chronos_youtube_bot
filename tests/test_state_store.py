"""Tests for modules/state_store.py — uses a throwaway temp SQLite file per test."""

import tempfile
import unittest
from pathlib import Path

from modules.state_store import StateStore


class StateStoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_chronos.db"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_table_creation_is_idempotent(self):
        store1 = StateStore(self.db_path)
        store1.close()
        # Reopening against the same file must not raise, and schema must
        # still be usable (CREATE TABLE IF NOT EXISTS re-runs cleanly).
        store2 = StateStore(self.db_path)
        store2.record_video(video_id="v1", title="Idempotent Test")
        self.assertIsNotNone(store2.get_video("v1"))
        store2.close()

    def test_insert_and_read_video(self):
        with StateStore(self.db_path) as store:
            store.record_video(
                video_id="abc123",
                topic="The Mystery of Roanoke",
                title="What Really Happened to Roanoke?",
                slug="roanoke-mystery",
                published_at="2026-01-15T10:00:00",
                privacy="private",
                category_id="28",
                local_path="/output/roanoke.mp4",
            )
            video = store.get_video("abc123")
            self.assertIsNotNone(video)
            self.assertEqual(video["video_id"], "abc123")
            self.assertEqual(video["topic"], "The Mystery of Roanoke")
            self.assertEqual(video["title"], "What Really Happened to Roanoke?")
            self.assertEqual(video["slug"], "roanoke-mystery")
            self.assertEqual(video["privacy"], "private")
            self.assertEqual(video["category_id"], "28")
            self.assertEqual(video["local_path"], "/output/roanoke.mp4")

    def test_list_videos(self):
        with StateStore(self.db_path) as store:
            store.record_video(video_id="v1", title="First", published_at="2026-01-01T00:00:00")
            store.record_video(video_id="v2", title="Second", published_at="2026-02-01T00:00:00")
            store.record_video(video_id="v3", title="Third", published_at="2026-03-01T00:00:00")

            all_videos = store.list_videos()
            self.assertEqual(len(all_videos), 3)
            # Most recently published first.
            self.assertEqual(all_videos[0]["video_id"], "v3")

            recent = store.list_videos(since="2026-02-01T00:00:00")
            self.assertEqual({v["video_id"] for v in recent}, {"v2", "v3"})

            limited = store.list_videos(limit=1)
            self.assertEqual(len(limited), 1)

    def test_metrics_snapshots_ordered_history(self):
        with StateStore(self.db_path) as store:
            store.record_video(video_id="v1", title="Test Video")
            store.record_metrics_snapshot(
                video_id="v1", snapshot_date="2026-01-03", views=300, likes=30,
                comment_count=3, watch_time_minutes=15.0, average_view_duration_seconds=45.0,
            )
            store.record_metrics_snapshot(
                video_id="v1", snapshot_date="2026-01-01", views=100, likes=10,
                comment_count=1, watch_time_minutes=5.0, average_view_duration_seconds=30.0,
            )
            store.record_metrics_snapshot(
                video_id="v1", snapshot_date="2026-01-02", views=200, likes=20,
                comment_count=2, watch_time_minutes=10.0, average_view_duration_seconds=40.0,
            )

            history = store.metrics_history("v1")
            self.assertEqual(len(history), 3)
            self.assertEqual(
                [row["snapshot_date"] for row in history],
                ["2026-01-01", "2026-01-02", "2026-01-03"],
            )
            self.assertEqual(history[0]["views"], 100)
            self.assertEqual(history[-1]["views"], 300)

    def test_latest_metrics_returns_most_recent(self):
        with StateStore(self.db_path) as store:
            store.record_video(video_id="v1", title="Test Video")
            store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-01-01", views=100)
            store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-01-05", views=500)
            store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-01-03", views=300)

            latest = store.latest_metrics("v1")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["snapshot_date"], "2026-01-05")
            self.assertEqual(latest["views"], 500)

    def test_metrics_snapshot_upsert_same_date(self):
        with StateStore(self.db_path) as store:
            store.record_video(video_id="v1", title="Test Video")
            store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-01-01", views=100)
            store.record_metrics_snapshot(video_id="v1", snapshot_date="2026-01-01", views=150)

            history = store.metrics_history("v1")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["views"], 150)

    def test_nonexistent_video_returns_none_or_empty(self):
        with StateStore(self.db_path) as store:
            self.assertIsNone(store.get_video("does-not-exist"))
            self.assertIsNone(store.latest_metrics("does-not-exist"))
            self.assertEqual(store.metrics_history("does-not-exist"), [])
            self.assertEqual(store.list_videos(), [])


if __name__ == "__main__":
    unittest.main()
