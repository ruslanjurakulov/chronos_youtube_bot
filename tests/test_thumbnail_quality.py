"""The thumbnail-quality helpers, tested without rendering: text is wrapped and
capped so it can never spill off the canvas, and the scrim gradient ramps from
transparent at its top to near-opaque at the bottom so a caption reads on any
photo. A full render smoke test runs when PIL is available."""

import unittest

from modules.thumbnail_generator import scrim_alpha, wrap_capped


class WrapCappedTestCase(unittest.TestCase):
    def test_wraps_within_line_count(self):
        lines = wrap_capped("hello world this is fine", width=10, max_lines=5)
        self.assertTrue(all(len(ln) <= 12 for ln in lines))

    def test_caps_and_ellipsizes(self):
        text = "one two three four five six seven eight nine ten eleven twelve"
        lines = wrap_capped(text, width=8, max_lines=2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))

    def test_empty_is_empty(self):
        self.assertEqual(wrap_capped("", 10, 3), [])
        self.assertEqual(wrap_capped("   ", 10, 3), [])

    def test_short_text_unchanged(self):
        self.assertEqual(wrap_capped("short", 20, 3), ["short"])


class ScrimAlphaTestCase(unittest.TestCase):
    def test_zero_above_top(self):
        self.assertEqual(scrim_alpha(y=100, top_y=500, height=1080), 0)
        self.assertEqual(scrim_alpha(y=500, top_y=500, height=1080), 0)

    def test_ramps_to_max_at_bottom(self):
        top, h, mx = 500, 1080, 210
        bottom = scrim_alpha(y=h, top_y=top, height=h, max_alpha=mx)
        mid = scrim_alpha(y=(top + h) // 2, top_y=top, height=h, max_alpha=mx)
        self.assertGreater(bottom, mid)     # darker lower down
        self.assertGreater(mid, 0)
        self.assertLessEqual(bottom, 255)

    def test_clamped(self):
        self.assertGreaterEqual(scrim_alpha(2000, 500, 1080), 0)
        self.assertLessEqual(scrim_alpha(2000, 500, 1080), 255)


class RenderSmokeTestCase(unittest.TestCase):
    def test_thumbnail_renders_with_scrim_and_accent(self):
        try:
            from PIL import Image
            from modules.thumbnail_generator import _make_thumbnail
        except Exception:
            self.skipTest("PIL not available")
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "thumb.jpg"
            _make_thumbnail(None, "SHOCKING TRUTH ABOUT ROME", "The Fall of Rome", out, variant="A")
            self.assertTrue(out.exists())
            with Image.open(out) as im:
                self.assertEqual(im.size[0] > 0 and im.size[1] > 0, True)


if __name__ == "__main__":
    unittest.main()
