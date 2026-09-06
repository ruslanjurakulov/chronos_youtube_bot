"""How many ffmpeg processes the render keeps alive.

Daily Video run #19 was killed at exit 143 with the runner shut down and four
orphaned ffmpeg processes left behind. The memory trace is what names the
cause: the Python process sat flat near 1 GB for the whole render while system
free memory fell from 6348 MB to 112 MB. Python was not the thing eating the
machine — its ffmpeg children were.

MoviePy 1.0.3 builds an AudioFileClip inside VideoFileClip unless it is told
not to, and that clip spawns an ffmpeg process of its own. The compositor was
constructing each reader and *then* calling `.without_audio()`, which discards
the audio but only after its process exists — so each of the twelve source
videos cost two decoders rather than one, and none of them could be closed
early because the composed clips pull frames lazily.

These tests pin the reader down to one process per file, and pin the encoder's
thread count, which is the other place 1080p frame buffers accumulate.
"""

import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.compositor import Compositor


class ReaderCost(unittest.TestCase):
    def setUp(self):
        self.comp = Compositor.__new__(Compositor)
        self.comp._readers = {}

    @patch("modules.compositor.VideoFileClip")
    def test_reader_is_opened_without_audio(self, VFC):
        """No audio decoder is created — not created and discarded, never created."""
        self.comp._open_video(Path("/tmp/a.mp4"))

        VFC.assert_called_once()
        _, kwargs = VFC.call_args
        self.assertIs(kwargs.get("audio"), False,
                      "VideoFileClip must be constructed with audio=False")
        # .without_audio() would mean the audio reader already existed.
        self.assertFalse(
            VFC.return_value.without_audio.called,
            "without_audio() discards an ffmpeg process that should never have been spawned",
        )

    @patch("modules.compositor.VideoFileClip")
    def test_one_reader_per_file_however_often_it_is_used(self, VFC):
        """The cache is what keeps a twelve-file pool from opening dozens."""
        for _ in range(4):
            self.comp._open_video(Path("/tmp/a.mp4"))
            self.comp._open_video(Path("/tmp/b.mp4"))

        self.assertEqual(VFC.call_count, 2)
        self.assertEqual(len(self.comp._readers), 2)

    def test_encoder_thread_count_is_capped(self):
        """Each x264 thread holds its own 1080p buffers; four was too many to
        hold beside a dozen decoders on a 7.9 GB runner."""
        source = inspect.getsource(Compositor.render)
        self.assertIn("threads=2", source)
        self.assertNotIn("threads=4", source)


if __name__ == "__main__":
    unittest.main()
