"""Tests for modules/publish_score.py.

The load-bearing property is honesty: a dimension with no signal scores None
(not 0), the overall is computed only over scored dimensions, and the module
never claims to be the publish gate.
"""

import unittest

from modules.publish_score import (
    DO_NOT_PUBLISH,
    HEURISTIC,
    IMPROVE,
    INSUFFICIENT,
    MEASURED,
    NONE,
    READY,
    PublishScore,
    ScoreInputs,
    evaluate,
)


def _dim(score: PublishScore, key: str):
    return next(d for d in score.dimensions if d.key == key)


class HeuristicDimensionsTestCase(unittest.TestCase):
    def test_strong_content_scores_high(self):
        r = evaluate(ScoreInputs(
            hook="Why nobody noticed this 500-year-old mistake?",
            title="The 500-Year-Old Mistake Nobody Noticed",
            description="A deep dive into the overlooked error that shaped history, " * 4,
            tags=("history", "mystery", "documentary", "facts", "ancient"),
            cta="Subscribe and watch the next one.",
            thumbnail_text="500-YEAR LIE",
        ))
        for key in ("hook", "seo", "cta", "thumbnail"):
            d = _dim(r, key)
            self.assertEqual(d.confidence, HEURISTIC)
            self.assertIsNotNone(d.score)
            self.assertGreaterEqual(d.score, 70)

    def test_missing_content_scores_none_not_zero(self):
        r = evaluate(ScoreInputs())  # nothing at all
        for key in ("hook", "seo", "cta", "thumbnail"):
            d = _dim(r, key)
            self.assertIsNone(d.score)  # None, never 0
            self.assertEqual(d.confidence, NONE)


class PredictionDimensionsTestCase(unittest.TestCase):
    def test_absent_signals_are_none(self):
        r = evaluate(ScoreInputs(hook="Why this?"))
        for key in ("retention", "ctr", "competition"):
            self.assertIsNone(_dim(r, key).score)
            self.assertEqual(_dim(r, key).confidence, NONE)

    def test_present_signals_are_measured(self):
        r = evaluate(ScoreInputs(
            hook="Why this?",
            past_retention_pct=50.0,
            past_ctr_pct=8.0,
            competitor_saturation=0.2,
        ))
        for key in ("retention", "ctr", "competition"):
            d = _dim(r, key)
            self.assertEqual(d.confidence, MEASURED)
            self.assertIsNotNone(d.score)
        # 50% retention → strong; 0.2 saturation → high opportunity.
        self.assertGreaterEqual(_dim(r, "retention").score, 80)
        self.assertGreaterEqual(_dim(r, "competition").score, 70)


class OverallAndVerdictTestCase(unittest.TestCase):
    def test_overall_only_uses_scored_dimensions(self):
        # Only content present → 4 of 7 dimensions inform the overall.
        r = evaluate(ScoreInputs(
            hook="Why nobody noticed this 500-year-old mistake?",
            title="The 500-Year-Old Mistake Nobody Noticed",
            description="x" * 200,
            tags=("a", "b", "c", "d", "e"),
            cta="Subscribe and watch the next one.",
            thumbnail_text="500-YEAR LIE",
        ))
        self.assertEqual(r.dims_total, 7)
        self.assertEqual(r.dims_scored, 4)
        self.assertIsNotNone(r.overall)
        self.assertEqual(r.verdict, READY)

    def test_insufficient_data_when_nothing_scored(self):
        r = evaluate(ScoreInputs())
        self.assertEqual(r.dims_scored, 0)
        self.assertIsNone(r.overall)
        self.assertEqual(r.verdict, INSUFFICIENT)

    def test_weak_content_does_not_publish(self):
        r = evaluate(ScoreInputs(hook="stuff", title="ok", cta="", thumbnail_text=""))
        # A bare hook + tiny title, nothing else — overall low.
        self.assertIn(r.verdict, {IMPROVE, DO_NOT_PUBLISH})

    def test_recommendations_collected_for_weak_dims(self):
        r = evaluate(ScoreInputs(hook="stuff"))
        self.assertTrue(any(r.notes))  # at least one "how to improve" note

    def test_metadata_shape(self):
        r = evaluate(ScoreInputs(hook="Why this?", past_retention_pct=40.0))
        md = r.to_metadata()
        self.assertEqual(set(md), {"overall", "verdict", "dims_scored", "dims_total", "dimensions"})
        self.assertIn("hook", md["dimensions"])
        self.assertEqual(md["dimensions"]["ctr"]["score"], None)


if __name__ == "__main__":
    unittest.main()
