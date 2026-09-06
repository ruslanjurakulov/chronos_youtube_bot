"""Put the rendered video, its title and its script where a human can see them.

Why this exists
---------------
Until now the only durable handle on a finished video was its YouTube id, and
every upload is private (``config.YOUTUBE_PRIVACY`` defaults to ``private``,
and so do both the schedule and the manual dispatch). A private video cannot be
embedded, and ``videos.local_path`` points at a runner that no longer exists —
so there was nothing for the Command Center to show. This module puts the mp4
in a private Supabase Storage bucket and records the script beside it, which is
what a reviewer actually needs in order to say yes.

What it deliberately does NOT do
--------------------------------
It does not publish, un-publish, or change any video's privacy, and it is not
part of the publish gate. It runs *after* the pipeline has finished with a
video and only ever writes: an object into a bucket, and two columns on a row.

Like ``event_log`` and ``supabase_sync``, nothing here raises into the
pipeline. A missing bucket, a slow network or an oversized file is logged and
swallowed — a preview is a convenience, and losing one must never turn a
successful run into a failed one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BUCKET = "previews"
_TIMEOUT = 180  # seconds — a whole video goes over the wire, not a JSON row.

# Supabase's own ceiling for this bucket is 500 MB (see migration 0004). We
# refuse well before it: a video that large means the render produced something
# unexpected, and pushing it would spend the storage quota on the wrong thing.
MAX_BYTES = 400 * 1024 * 1024

# Free-tier storage is 1 GB, and a five-minute 1080p cut is 50-150 MB. Keeping
# the last few per channel is the difference between a working review queue and
# a quota that fills up silently in a fortnight.
KEEP_PER_CHANNEL = 5


class VideoReview:
    """Uploads previews and prunes old ones. Disabled, and harmless, without keys."""

    def __init__(self, url: str | None = None, service_key: str | None = None):
        self.url = (url if url is not None else os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key if service_key is not None else os.getenv("SUPABASE_SERVICE_KEY", "")
        self.enabled = bool(self.url and self.service_key)
        if not self.enabled:
            logger.info(
                "VideoReview disabled (SUPABASE_URL / SUPABASE_SERVICE_KEY not set) — "
                "the run is unaffected; there will simply be no preview to review."
            )

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
        }
        if extra:
            headers.update(extra)
        return headers

    # ── storage ────────────────────────────────────────────────────────────
    def upload_preview(self, video_path: Path, channel_id: str, video_id: str) -> str | None:
        """Put the mp4 in the bucket. Returns its object path, or None."""
        if not self.enabled:
            return None
        try:
            size = video_path.stat().st_size
        except OSError:
            logger.warning("No preview uploaded: cannot stat %s", video_path)
            return None
        if size > MAX_BYTES:
            logger.warning(
                "No preview uploaded: %s is %.0f MB, over the %.0f MB ceiling",
                video_path.name, size / 1048576, MAX_BYTES / 1048576,
            )
            return None

        # Keyed on the YouTube id so the object and the row can never drift
        # apart, and re-running the same video overwrites rather than piles up.
        object_path = f"{channel_id}/{video_id}.mp4"
        try:
            with video_path.open("rb") as fh:
                resp = requests.post(
                    f"{self.url}/storage/v1/object/{BUCKET}/{object_path}",
                    data=fh,
                    headers=self._headers({
                        "Content-Type": "video/mp4",
                        # Overwrite an existing object instead of failing on it.
                        "x-upsert": "true",
                    }),
                    timeout=_TIMEOUT,
                )
            if resp.status_code >= 300:
                logger.warning("Preview upload failed (%s) — the run is unaffected", resp.status_code)
                return None
        except Exception as e:
            logger.warning("Preview upload failed (%s: %s) — the run is unaffected", type(e).__name__, e)
            return None

        logger.info("Preview stored: %s (%.0f MB)", object_path, size / 1048576)
        return object_path

    def prune(self, channel_id: str) -> int:
        """Delete all but the newest KEEP_PER_CHANNEL previews for one channel."""
        if not self.enabled:
            return 0
        try:
            rows = requests.get(
                f"{self.url}/rest/v1/videos",
                params={
                    "select": "video_id,preview_path,published_at",
                    "channel_id": f"eq.{channel_id}",
                    "preview_path": "not.is.null",
                    "order": "published_at.desc",
                    "offset": str(KEEP_PER_CHANNEL),
                },
                headers=self._headers(),
                timeout=30,
            )
            rows.raise_for_status()
            stale = [r for r in rows.json() if r.get("preview_path")]
        except Exception as e:
            logger.warning("Could not list old previews (%s: %s)", type(e).__name__, e)
            return 0
        if not stale:
            return 0

        try:
            resp = requests.delete(
                f"{self.url}/storage/v1/object/{BUCKET}",
                json={"prefixes": [r["preview_path"] for r in stale]},
                headers=self._headers({"Content-Type": "application/json"}),
                timeout=60,
            )
            if resp.status_code >= 300:
                logger.warning("Could not delete old previews (%s)", resp.status_code)
                return 0
        except Exception as e:
            logger.warning("Could not delete old previews (%s: %s)", type(e).__name__, e)
            return 0

        # Clear the pointers too, so the dashboard never offers a play button
        # for bytes that are gone.
        for r in stale:
            self._patch_video(r["video_id"], {"preview_path": None})
        logger.info("Pruned %d old preview(s) for channel %s", len(stale), channel_id)
        return len(stale)

    def fetch_auto_publish(self, channel_id: str) -> bool:
        """Does this channel publish without being asked?

        Read from Supabase rather than the local registry, because the toggle
        lives in the Command Center and that is where an operator turns it on.
        Anything that goes wrong — no keys, no network, no column yet — answers
        False, which leaves the video waiting for a human. The safe direction is
        the default in every failure mode.
        """
        if not self.enabled:
            return False
        try:
            resp = requests.get(
                f"{self.url}/rest/v1/channels",
                params={"select": "auto_publish", "channel_id": f"eq.{channel_id}", "limit": "1"},
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            rows = resp.json()
            return bool(rows and rows[0].get("auto_publish"))
        except Exception as e:
            logger.info(
                "Could not read auto_publish for %s (%s) — treating it as off",
                channel_id, type(e).__name__,
            )
            return False

    # ── the row ────────────────────────────────────────────────────────────
    def _patch_video(self, video_id: str, patch: dict) -> bool:
        try:
            resp = requests.patch(
                f"{self.url}/rest/v1/videos",
                params={"video_id": f"eq.{video_id}"},
                json=patch,
                headers=self._headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
                timeout=30,
            )
            return resp.status_code < 300
        except Exception as e:
            logger.warning("Could not update video %s (%s: %s)", video_id, type(e).__name__, e)
            return False

    def record(
        self,
        *,
        video_id: str,
        channel_id: str,
        video_path: Path,
        script_text: str,
        auto_publish: bool,
    ) -> None:
        """Upload the preview and attach the script to the row.

        `review_state` is left alone when the channel publishes automatically —
        there is nobody waiting on it — and set to "pending" when it does not,
        which is the honest statement that a human has not looked yet.
        """
        if not self.enabled:
            return
        preview_path = self.upload_preview(video_path, channel_id, video_id)
        patch: dict = {"script_text": script_text or None}
        if preview_path:
            patch["preview_path"] = preview_path
        patch["review_state"] = "approved" if auto_publish else "pending"
        self._patch_video(video_id, patch)
        if preview_path:
            self.prune(channel_id)
