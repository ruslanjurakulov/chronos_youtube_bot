"""What the review mirror does, and — more importantly — what it refuses to do.

The whole point of this module is that a human sees the video before it goes
public. That only holds if every failure leans the same way: when anything is
unknown or broken, the video waits. These tests pin that direction down, and
pin the promise that nothing here publishes.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.video_review import MAX_BYTES, VideoReview


class Disabled(unittest.TestCase):
    """Without keys the module is inert — the run must be unaffected."""

    def setUp(self):
        self.r = VideoReview(url="", service_key="")

    def test_is_disabled(self):
        self.assertFalse(self.r.enabled)

    def test_upload_is_a_no_op(self):
        self.assertIsNone(self.r.upload_preview(Path("/tmp/x.mp4"), "c", "v"))

    def test_auto_publish_reads_false(self):
        """No keys must not read as 'this channel publishes by itself'."""
        self.assertFalse(self.r.fetch_auto_publish("c"))

    def test_record_does_nothing(self):
        # Would raise on a missing file if it got as far as touching one.
        self.r.record(video_id="v", channel_id="c", video_path=Path("/nope.mp4"),
                      script_text="x", auto_publish=False)


class SafeDirection(unittest.TestCase):
    def setUp(self):
        self.r = VideoReview(url="https://x.supabase.co", service_key="k")

    @patch("modules.video_review.requests.get", side_effect=OSError("network down"))
    def test_auto_publish_is_false_when_the_lookup_fails(self, _):
        """An outage must never be read as permission to publish."""
        self.assertFalse(self.r.fetch_auto_publish("c"))

    @patch("modules.video_review.requests.get")
    def test_auto_publish_is_false_when_the_column_is_absent(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: [{}])
        get.return_value.raise_for_status = lambda: None
        self.assertFalse(self.r.fetch_auto_publish("c"))

    @patch("modules.video_review.requests.get")
    def test_auto_publish_is_true_only_when_it_says_so(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: [{"auto_publish": True}])
        get.return_value.raise_for_status = lambda: None
        self.assertTrue(self.r.fetch_auto_publish("c"))

    @patch("modules.video_review.requests.post")
    def test_an_oversized_render_is_refused_rather_than_uploaded(self, post):
        big = MagicMock()
        big.stat.return_value = MagicMock(st_size=MAX_BYTES + 1)
        self.assertIsNone(self.r.upload_preview(big, "c", "v"))
        post.assert_not_called()

    @patch("modules.video_review.requests.post", side_effect=OSError("boom"))
    def test_a_failed_upload_returns_none_instead_of_raising(self, _):
        f = MagicMock()
        f.stat.return_value = MagicMock(st_size=1024)
        f.open = MagicMock()
        self.assertIsNone(self.r.upload_preview(f, "c", "v"))


class ReviewStateFollowsTheChannel(unittest.TestCase):
    def setUp(self):
        self.r = VideoReview(url="https://x.supabase.co", service_key="k")
        self.r.upload_preview = MagicMock(return_value=None)
        self.r.prune = MagicMock()
        self.r._patch_video = MagicMock(return_value=True)

    def test_manual_channel_leaves_the_video_pending(self):
        self.r.record(video_id="v", channel_id="c", video_path=Path("/x.mp4"),
                      script_text="the narration", auto_publish=False)
        patch_arg = self.r._patch_video.call_args[0][1]
        self.assertEqual(patch_arg["review_state"], "pending")
        self.assertEqual(patch_arg["script_text"], "the narration")

    def test_auto_channel_has_nothing_waiting(self):
        self.r.record(video_id="v", channel_id="c", video_path=Path("/x.mp4"),
                      script_text="x", auto_publish=True)
        self.assertEqual(self.r._patch_video.call_args[0][1]["review_state"], "approved")

    def test_it_only_ever_writes_those_three_fields(self):
        """No privacy, no status, no publish. The mirror does not act."""
        self.r.record(video_id="v", channel_id="c", video_path=Path("/x.mp4"),
                      script_text="x", auto_publish=False)
        keys = set(self.r._patch_video.call_args[0][1])
        self.assertEqual(keys, {"script_text", "review_state"})


if __name__ == "__main__":
    unittest.main()
