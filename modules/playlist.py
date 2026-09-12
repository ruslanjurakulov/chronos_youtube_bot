"""Series playlist — add each published video to its series' playlist.

A playlist keeps a series bingeable and lifts session time: one video pulls the
viewer into the next. After a video publishes, if its series names a playlist,
the video is appended to it.

Strictly best-effort and downstream of a successful publish: the video is
already live, so nothing here may turn a good run into a failed one. Every call
degrades — a missing playlist id is a no-op, an API error is logged and
swallowed. It never publishes, never gates, and never retries in a way that
could double-add.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_playlist_id(series_obj=None) -> str:
    """The playlist a run's video should join, or "" for none. Today that is the
    series' own playlist_id; a channel-level default can be layered here later
    without touching call sites."""
    pid = getattr(series_obj, "playlist_id", "") if series_obj is not None else ""
    return str(pid or "").strip()


def add_video_to_playlist(service, playlist_id: str, video_id: str) -> Optional[str]:
    """Append `video_id` to `playlist_id` via YouTube playlistItems.insert.

    Returns the new playlistItem id on success, or None when it was skipped
    (missing id/service) or failed. Never raises — a playlist error must not
    sink a run whose video already published. ~50 quota units."""
    playlist_id = str(playlist_id or "").strip()
    video_id = str(video_id or "").strip()
    if not service or not playlist_id or not video_id:
        return None
    try:
        request = service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        )
        resp = request.execute()
        item_id = resp.get("id") if isinstance(resp, dict) else None
        logger.info("Added video %s to playlist %s (item %s)", video_id, playlist_id, item_id)
        return item_id
    except Exception as e:
        logger.warning(
            "Could not add video %s to playlist %s (%s: %s) — the video is already published",
            video_id, playlist_id, type(e).__name__, e,
        )
        return None
