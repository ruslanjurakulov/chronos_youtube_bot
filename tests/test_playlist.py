"""The series playlist add is best-effort and downstream of a live video: it
returns an id on success, no-ops on a missing playlist/id, and swallows any API
error (a playlist failure must never sink a run whose video already published)."""

import unittest

from modules.playlist import add_video_to_playlist, resolve_playlist_id
from modules.series import Series


class _FakeRequest:
    def __init__(self, result=None, boom=False):
        self._result = result
        self._boom = boom

    def execute(self):
        if self._boom:
            raise RuntimeError("api error")
        return self._result


class _FakeService:
    def __init__(self, result=None, boom=False):
        self._result = result
        self._boom = boom
        self.calls = []

    def playlistItems(self):
        return self

    def insert(self, part=None, body=None):
        self.calls.append({"part": part, "body": body})
        return _FakeRequest(self._result, self._boom)


class ResolvePlaylistTestCase(unittest.TestCase):
    def test_series_playlist_id(self):
        s = Series(series_id="s1", playlist_id="PL123")
        self.assertEqual(resolve_playlist_id(s), "PL123")

    def test_none_series_is_empty(self):
        self.assertEqual(resolve_playlist_id(None), "")

    def test_blank_playlist_is_empty(self):
        self.assertEqual(resolve_playlist_id(Series(series_id="s1")), "")


class AddToPlaylistTestCase(unittest.TestCase):
    def test_happy_path_returns_item_id(self):
        svc = _FakeService(result={"id": "PLI_1"})
        item = add_video_to_playlist(svc, "PL123", "vid1")
        self.assertEqual(item, "PLI_1")
        body = svc.calls[0]["body"]
        self.assertEqual(body["snippet"]["playlistId"], "PL123")
        self.assertEqual(body["snippet"]["resourceId"]["videoId"], "vid1")

    def test_missing_inputs_are_noops(self):
        svc = _FakeService(result={"id": "x"})
        self.assertIsNone(add_video_to_playlist(svc, "", "vid1"))
        self.assertIsNone(add_video_to_playlist(svc, "PL123", ""))
        self.assertIsNone(add_video_to_playlist(None, "PL123", "vid1"))
        self.assertEqual(svc.calls, [])  # nothing was attempted

    def test_api_error_is_swallowed(self):
        svc = _FakeService(boom=True)
        # Must not raise — the video is already published.
        self.assertIsNone(add_video_to_playlist(svc, "PL123", "vid1"))


class SeriesPlaylistFieldTestCase(unittest.TestCase):
    def test_from_row_reads_playlist_id_absent_is_empty(self):
        self.assertEqual(Series.from_row({"series_id": "s1"}).playlist_id, "")
        self.assertEqual(Series.from_row({"series_id": "s1", "playlist_id": "PLx"}).playlist_id, "PLx")

    def test_roundtrip(self):
        s = Series(series_id="s1", playlist_id="PLx")
        self.assertEqual(Series.from_row(s.to_dict()).playlist_id, "PLx")


if __name__ == "__main__":
    unittest.main()
