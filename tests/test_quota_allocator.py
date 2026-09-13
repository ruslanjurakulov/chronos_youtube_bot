"""Quota allocator: split a day's upload budget across channels by measured
performance while reserving a baseline for each. Rules under test: the result is
whole numbers summing to exactly the budget, stronger channels get more, a new
(unmeasured) channel still gets its baseline (null ≠ 0), and views-per-day keeps
an old catalogue from dominating."""

import unittest
from datetime import datetime, timedelta, timezone

from modules import quota_allocator as qa

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class AllocateTestCase(unittest.TestCase):
    def test_sums_to_exact_budget(self):
        out = qa.allocate({"a": 5.0, "b": 3.0, "c": 1.0}, 10)
        self.assertEqual(sum(out.values()), 10)

    def test_stronger_channel_gets_more(self):
        out = qa.allocate({"a": 10.0, "b": 1.0}, 12, min_per_channel=1)
        self.assertGreater(out["a"], out["b"])

    def test_baseline_reserved_for_zero_score(self):
        # A new channel (score 0) still gets its reserved slot.
        out = qa.allocate({"strong": 100.0, "newbie": 0.0}, 10, min_per_channel=1)
        self.assertGreaterEqual(out["newbie"], 1)
        self.assertEqual(sum(out.values()), 10)

    def test_all_zero_scores_split_evenly(self):
        out = qa.allocate({"a": 0.0, "b": 0.0, "c": 0.0}, 9)
        self.assertEqual(out, {"a": 3, "b": 3, "c": 3})

    def test_more_channels_than_slots(self):
        out = qa.allocate({"a": 1.0, "b": 1.0, "c": 1.0}, 2, min_per_channel=1)
        self.assertEqual(sum(out.values()), 2)          # exact
        self.assertTrue(all(v in (0, 1) for v in out.values()))

    def test_zero_budget_is_all_zero(self):
        self.assertEqual(qa.allocate({"a": 5.0}, 0), {"a": 0})

    def test_no_channels(self):
        self.assertEqual(qa.allocate({}, 10), {})

    def test_negative_scores_treated_as_zero(self):
        out = qa.allocate({"a": -5.0, "b": 4.0}, 10, min_per_channel=1)
        self.assertGreater(out["b"], out["a"])
        self.assertEqual(sum(out.values()), 10)


class PerformanceScoresTestCase(unittest.TestCase):
    def _v(self, vid, days_old, fmt="long"):
        return {"video_id": vid, "published_at": (NOW - timedelta(days=days_old)).isoformat(),
                "video_format": fmt}

    def test_views_per_day_not_raw_views(self):
        videos_by_channel = {
            "old": [self._v("o1", 100)],   # 10000 views over 100 days = 100/day
            "new": [self._v("n1", 2)],     # 1000 views over 2 days = 500/day
        }
        metrics = {"o1": {"views": 10000}, "n1": {"views": 1000}}
        scores = qa.performance_scores(videos_by_channel, metrics, now=NOW)
        self.assertGreater(scores["new"], scores["old"])  # rate beats total

    def test_unmeasured_channel_scores_zero(self):
        videos_by_channel = {"measured": [self._v("m1", 10)], "empty": []}
        scores = qa.performance_scores(videos_by_channel, {"m1": {"views": 1000}}, now=NOW)
        self.assertEqual(scores["empty"], 0.0)
        self.assertGreater(scores["measured"], 0.0)

    def test_shorts_ignored(self):
        videos_by_channel = {"c": [self._v("s1", 10, fmt="short")]}
        scores = qa.performance_scores(videos_by_channel, {"s1": {"views": 99999}}, now=NOW)
        self.assertEqual(scores["c"], 0.0)


class _FakeStore:
    def __init__(self, videos_by_channel, metrics):
        self._v = videos_by_channel
        self._m = metrics

    def list_videos(self, limit=100, channel_id=None):
        return self._v.get(channel_id, [])

    def latest_metrics(self, video_id):
        return self._m.get(video_id)


class RecommendAllocationTestCase(unittest.TestCase):
    def test_end_to_end(self):
        vbc = {
            "a": [{"video_id": "a1", "published_at": (NOW - timedelta(days=5)).isoformat(),
                   "video_format": "long"}],
            "b": [{"video_id": "b1", "published_at": (NOW - timedelta(days=5)).isoformat(),
                   "video_format": "long"}],
        }
        store = _FakeStore(vbc, {"a1": {"views": 10000}, "b1": {"views": 500}})
        out = qa.recommend_allocation(store, ["a", "b"], 10, now=NOW)
        self.assertEqual(sum(out.values()), 10)
        self.assertGreater(out["a"], out["b"])

    def test_read_failure_scores_zero_but_still_allocates(self):
        class Boom:
            def list_videos(self, limit=100, channel_id=None):
                raise RuntimeError("db down")
            def latest_metrics(self, video_id):
                return None
        out = qa.recommend_allocation(Boom(), ["a", "b"], 4, now=NOW)
        self.assertEqual(sum(out.values()), 4)  # even split, never raises


if __name__ == "__main__":
    unittest.main()
