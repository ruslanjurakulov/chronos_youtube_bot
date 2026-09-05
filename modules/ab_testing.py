"""Thumbnail and title A/B — actually shipping the variant, and reading it back.

The gap this closes
-------------------
The pipeline has always generated two thumbnails and two titles, then uploaded
thumbnail A with title A every single time. The B variant was rendered, written
to disk, and thrown away. Click-through rate is the largest single lever on how
many people watch a video, and the experiment that would measure it was being
discarded before it ran.

How the variant is chosen
-------------------------
Strict alternation by the channel's own published-video count: even → A, odd →
B. Deterministic, needs no extra state, and gives both arms a balanced sample
without a random-number generator that could drift.

Once there is enough evidence, selection *leans* toward the winner — but never
to the point of stopping the experiment. `EXPLORE_EVERY` keeps one video in
five on the losing arm, so a winning variant that stops working is noticed
instead of being locked in forever.

Reading it back
---------------
`variant_performance` compares mean CTR per arm from `metrics_snapshots`, and
refuses to name a winner below `MIN_PER_VARIANT` measured videos or below
`MIN_LIFT` relative difference. A conclusion drawn from two videos is not a
conclusion, and neither is a 1% gap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

VARIANT_A = "A"
VARIANT_B = "B"

#: Measured videos required *per arm* before a winner is named at all.
MIN_PER_VARIANT = 5
#: Relative difference required to call it. Below this the arms are a tie.
MIN_LIFT = 0.10
#: Even with a winner, one video in this many stays on the other arm.
EXPLORE_EVERY = 5


@dataclass(frozen=True)
class VariantStats:
    variant: str
    videos: int
    #: Mean impression CTR across measured videos, or None when none were measured.
    mean_ctr: Optional[float]
    impressions: int


@dataclass(frozen=True)
class ABResult:
    a: VariantStats
    b: VariantStats
    #: "A", "B", or None — None means "not enough evidence", never "they're equal".
    winner: Optional[str]
    reason: str

    @property
    def decided(self) -> bool:
        return self.winner is not None


def choose_variant(published_count: int, result: Optional[ABResult] = None) -> str:
    """Which arm the next video should ship on.

    With no verdict yet this is strict alternation, so the two arms fill up at
    the same rate. With a verdict it favours the winner but keeps exploring —
    a thumbnail style that worked in June is not guaranteed to work in December,
    and an experiment that stops running stops being able to tell you.
    """
    try:
        count = int(published_count)
    except (TypeError, ValueError):
        count = 0
    if count < 0:
        count = 0

    if result is None or not result.decided:
        return VARIANT_A if count % 2 == 0 else VARIANT_B

    explore = count % EXPLORE_EVERY == (EXPLORE_EVERY - 1)
    loser = VARIANT_B if result.winner == VARIANT_A else VARIANT_A
    return loser if explore else str(result.winner)


def variant_performance(videos: list, snapshots: list) -> ABResult:
    """Compare the two arms using real click-through, or say there isn't enough.

    `videos` are rows carrying `thumbnail_variant`; `snapshots` are
    metrics_snapshots rows carrying `impression_ctr`. Only the latest snapshot
    per video counts, and a video with no measured CTR is excluded rather than
    counted as zero — an unpolled video has *unknown* click-through.
    """
    latest: dict = {}
    for snap in snapshots or []:
        video_id = snap.get("video_id")
        if not video_id:
            continue
        seen = latest.get(video_id)
        if seen is None or str(snap.get("snapshot_date", "")) > str(seen.get("snapshot_date", "")):
            latest[video_id] = snap

    buckets: dict = {VARIANT_A: [], VARIANT_B: []}
    for video in videos or []:
        variant = (video.get("thumbnail_variant") or "").upper()
        if variant not in buckets:
            continue
        snap = latest.get(video.get("video_id"))
        if not snap:
            continue
        ctr = snap.get("impression_ctr")
        if ctr is None:
            continue  # measured views but no CTR — unknown, not zero
        buckets[variant].append((float(ctr), int(snap.get("impressions") or 0)))

    stats = {v: _stats(v, rows) for v, rows in buckets.items()}
    a, b = stats[VARIANT_A], stats[VARIANT_B]

    if a.videos < MIN_PER_VARIANT or b.videos < MIN_PER_VARIANT:
        return ABResult(
            a=a, b=b, winner=None,
            reason=(
                f"needs {MIN_PER_VARIANT} measured videos per variant; "
                f"A has {a.videos}, B has {b.videos}"
            ),
        )
    if a.mean_ctr is None or b.mean_ctr is None:
        return ABResult(a=a, b=b, winner=None, reason="no click-through measured yet")

    high, low = max(a.mean_ctr, b.mean_ctr), min(a.mean_ctr, b.mean_ctr)
    if low <= 0:
        return ABResult(a=a, b=b, winner=None, reason="a variant measured zero click-through")
    lift = (high - low) / low
    if lift < MIN_LIFT:
        return ABResult(
            a=a, b=b, winner=None,
            reason=f"only {lift:.0%} apart; under the {MIN_LIFT:.0%} floor this is a tie",
        )

    winner = VARIANT_A if a.mean_ctr >= b.mean_ctr else VARIANT_B
    return ABResult(
        a=a, b=b, winner=winner,
        reason=f"{winner} leads by {lift:.0%} over {a.videos + b.videos} measured videos",
    )


def _stats(variant: str, rows: list) -> VariantStats:
    if not rows:
        return VariantStats(variant=variant, videos=0, mean_ctr=None, impressions=0)
    return VariantStats(
        variant=variant,
        videos=len(rows),
        mean_ctr=round(sum(ctr for ctr, _ in rows) / len(rows), 6),
        impressions=sum(impressions for _, impressions in rows),
    )
