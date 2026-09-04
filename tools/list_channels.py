#!/usr/bin/env python3
"""Emit the channels a scheduled run should cover, as a GitHub Actions matrix.

    python tools/list_channels.py --due-hour 15
    -> {"include": [{"channel_id": "default", "name": "Chronos", "niche": "..."}]}

The daily workflow calls this once, then fans out one job per returned channel
with ``fail-fast: false``, so a credential failure on one channel cannot cancel
another channel's video.

Two safety properties matter here:

* **It never returns a PAUSED channel.** `ChannelRegistry.active()` filters on
  status AND schedule.enabled, so pausing a channel in the Command Center is
  what actually stops it being scheduled.
* **It cannot fail the workflow open.** If the registry cannot be loaded at
  all, it falls back to the default channel — the single channel this bot has
  always published — rather than emitting an empty matrix that would silently
  stop production, or every channel it half-read.

`--due-hour` filters to channels whose `schedule.publish_hour_utc` matches. A
channel with no hour set is treated as due at the default 15:00 UTC slot, which
is when the workflow has always run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.channels import DEFAULT_CHANNEL_ID, ChannelRegistry, legacy_default_channel  # noqa: E402

DEFAULT_HOUR_UTC = 15


def due_channels(due_hour: int | None = None, registry=None) -> list[dict]:
    try:
        registry = registry or ChannelRegistry()
        channels = registry.active()
    except Exception as e:  # pragma: no cover - defensive, see module docstring
        print(f"warning: channel registry unavailable ({type(e).__name__}: {e})", file=sys.stderr)
        channels = [legacy_default_channel()]

    if not channels:
        print("warning: no active channels resolved — falling back to the default", file=sys.stderr)
        channels = [legacy_default_channel()]

    if due_hour is not None:
        channels = [
            c
            for c in channels
            if (c.schedule.publish_hour_utc if c.schedule.publish_hour_utc is not None else DEFAULT_HOUR_UTC)
            == due_hour
        ]

    return [
        {
            "channel_id": str(c.channel_id),
            "name": c.name,
            "niche": c.niche,
            "is_default": str(c.channel_id) == str(DEFAULT_CHANNEL_ID),
        }
        for c in channels
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="List channels due for a scheduled run")
    parser.add_argument("--due-hour", type=int, default=None, help="Only channels scheduled at this UTC hour")
    parser.add_argument("--all", action="store_true", help="Every channel, including PAUSED ones")
    args = parser.parse_args()

    if args.all:
        rows = [
            {"channel_id": str(c.channel_id), "name": c.name, "niche": c.niche, "status": c.status}
            for c in ChannelRegistry().list()
        ]
    else:
        rows = due_channels(args.due_hour)

    print(json.dumps({"include": rows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
