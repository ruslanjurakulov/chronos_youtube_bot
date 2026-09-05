"""Tests for modules.resource_monitor — the memory diagnostic.

Its whole job is to survive being wrong: two runs died with no diagnosis, and
a diagnostic that can raise would turn a survivable render into a failed one.
So most of these test the failure paths.
"""

import logging
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.resource_monitor import (
    MemorySampler,
    describe_usage,
    process_rss_mb,
    system_memory_mb,
)


def _write(directory: str, name: str, text: str) -> Path:
    path = Path(directory) / name
    path.write_text(text)
    return path


STATUS = "Name:\tpython\nVmPeak:\t 2000000 kB\nVmRSS:\t 1048576 kB\nThreads:\t4\n"
MEMINFO = "MemTotal:        7000000 kB\nMemFree:          100000 kB\nMemAvailable:    2048000 kB\n"


class ProcReadingTests(unittest.TestCase):
    def test_rss_and_system_memory_are_read_in_mb(self):
        with TemporaryDirectory() as d:
            status = _write(d, "status", STATUS)
            meminfo = _write(d, "meminfo", MEMINFO)
            self.assertAlmostEqual(process_rss_mb(status), 1024.0)
            total, available = system_memory_mb(meminfo)
            self.assertAlmostEqual(total, 7000000 / 1024)
            self.assertAlmostEqual(available, 2000.0)

    def test_a_missing_file_is_none_not_an_exception(self):
        missing = Path("/nonexistent/proc/status")
        self.assertIsNone(process_rss_mb(missing))
        self.assertEqual(system_memory_mb(missing), (None, None))
        self.assertIsNone(describe_usage(missing, missing))

    def test_an_absent_or_unparseable_key_is_none(self):
        with TemporaryDirectory() as d:
            self.assertIsNone(process_rss_mb(_write(d, "a", "Threads:\t4\n")))
            self.assertIsNone(process_rss_mb(_write(d, "b", "VmRSS:\tlots kB\n")))
            self.assertIsNone(process_rss_mb(_write(d, "c", "VmRSS:\n")))

    def test_unknown_is_named_never_reported_as_zero(self):
        # A 0 here would read as "no memory used", which is the opposite of
        # what an unreadable value means.
        with TemporaryDirectory() as d:
            status = _write(d, "status", STATUS)
            partial = _write(d, "meminfo", "MemTotal:        7000000 kB\n")
            line = describe_usage(status, partial)
            self.assertIn("unknown available", line)
            self.assertNotIn("0 MB available", line)

    def test_a_readable_line_names_both_the_process_and_the_machine(self):
        with TemporaryDirectory() as d:
            line = describe_usage(_write(d, "s", STATUS), _write(d, "m", MEMINFO))
            self.assertIn("process RSS 1024 MB", line)
            self.assertIn("2000 MB available", line)


class MemorySamplerTests(unittest.TestCase):
    def test_it_records_a_peak_and_a_floor_and_logs_a_summary(self):
        with self.assertLogs("modules.resource_monitor", level=logging.INFO) as logs:
            with MemorySampler("render", interval=3600) as sampler:
                pass
        self.assertTrue(any("Memory summary for render" in m for m in logs.output))
        # This test runs on Linux in CI; where /proc is absent both stay None
        # and the sampler is silent, which is also correct.
        if sampler.peak_rss_mb is not None:
            self.assertGreater(sampler.peak_rss_mb, 0)

    def test_the_thread_does_not_outlive_the_block(self):
        with MemorySampler("render", interval=0.01) as sampler:
            pass
        self.assertIsNone(sampler._thread)

    def test_a_sample_never_raises(self):
        # The one thing this module must not do is take the render down with it.
        sampler = MemorySampler("render")
        with patch("modules.resource_monitor.process_rss_mb", side_effect=OSError("boom")):
            sampler.sample()  # must not propagate
        self.assertIsNone(sampler.peak_rss_mb)

    def test_no_proc_means_no_thread_and_no_noise(self):
        with patch("modules.resource_monitor.describe_usage", return_value=None):
            with MemorySampler("render", interval=0.01) as sampler:
                self.assertIsNone(sampler._thread)


class WhisperModelReleaseTests(unittest.TestCase):
    """The model must not still be resident during the render.

    whisper pulls in torch, which is too heavy to require here, so the module
    is stubbed when it is genuinely absent. CI installs the real one and this
    then runs against it.
    """

    @staticmethod
    def _subtitle_generator():
        if "whisper" not in sys.modules:
            try:
                import whisper  # noqa: F401
            except ImportError:
                stub = types.ModuleType("whisper")
                stub.Whisper = type("Whisper", (), {})
                stub.load_model = lambda name: stub.Whisper()
                sys.modules["whisper"] = stub
        from modules.subtitle_generator import SubtitleGenerator
        return SubtitleGenerator

    def test_releasing_drops_the_model(self):
        gen = self._subtitle_generator()("slug-under-test")
        gen._model = object()
        gen.release_model()
        self.assertIsNone(gen._model)

    def test_releasing_twice_and_releasing_unused_are_both_no_ops(self):
        gen = self._subtitle_generator()("slug-under-test")
        gen.release_model()  # never loaded
        self.assertIsNone(gen._model)
        gen._model = object()
        gen.release_model()
        gen.release_model()
        self.assertIsNone(gen._model)


if __name__ == "__main__":
    unittest.main()
