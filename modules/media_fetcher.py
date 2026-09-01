"""Stage 4: Media Fetcher — Pexels HD Videos + Ken Burns Images."""

import logging
import random
import time
from pathlib import Path

import requests
from PIL import Image

from config import (
    OUTPUT_DIR,
    PEXELS_API_KEY,
    PEXELS_PER_PAGE,
    PEXELS_VIDEO_ORIENTATION,
    PEXELS_VIDEO_QUALITY,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)

logger = logging.getLogger(__name__)

PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"

# Pexels quality priority order
QUALITY_PRIORITY = ["uhd", "hd", "sd"]


class MediaFetcher:
    def __init__(self, topic_slug: str):
        self.slug = topic_slug
        self.video_dir = OUTPUT_DIR / topic_slug / "media" / "videos"
        self.image_dir = OUTPUT_DIR / topic_slug / "media" / "images"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": PEXELS_API_KEY})

    # ------------------------------------------------------------------ Pexels Videos

    def _pexels_video_search(self, query: str, page: int = 1) -> list[dict]:
        params = {
            "query": query,
            "orientation": PEXELS_VIDEO_ORIENTATION,
            "size": "large",
            "per_page": PEXELS_PER_PAGE,
            "page": page,
        }
        resp = self.session.get(PEXELS_VIDEO_API, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("videos", [])

    def _best_video_file(self, video: dict) -> str | None:
        files = video.get("video_files", [])
        for quality in QUALITY_PRIORITY:
            for f in files:
                if f.get("quality") == quality and f.get("width", 0) >= VIDEO_WIDTH:
                    return f["link"]
        # Fallback: largest resolution
        files_sorted = sorted(files, key=lambda f: f.get("width", 0), reverse=True)
        return files_sorted[0]["link"] if files_sorted else None

    def _download(self, url: str, dest: Path) -> bool:
        if dest.exists():
            return True
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.warning("Download failed %s: %s", url, e)
            dest.unlink(missing_ok=True)
            return False

    def fetch_videos(self, keywords: list[str], count: int = 10) -> list[Path]:
        """Fetch `count` unique HD videos for the given keywords."""
        paths: list[Path] = []
        used_ids: set[int] = set()

        for keyword in keywords:
            if len(paths) >= count:
                break
            try:
                videos = self._pexels_video_search(keyword)
                random.shuffle(videos)
                for v in videos:
                    if len(paths) >= count:
                        break
                    vid_id = v["id"]
                    if vid_id in used_ids:
                        continue
                    link = self._best_video_file(v)
                    if not link:
                        continue
                    ext = "mp4"
                    dest = self.video_dir / f"{vid_id}.{ext}"
                    if self._download(link, dest):
                        paths.append(dest)
                        used_ids.add(vid_id)
                        logger.debug("Video: %s", dest.name)
                time.sleep(0.3)
            except Exception as e:
                logger.warning("Pexels video error for '%s': %s", keyword, e)

        logger.info("Fetched %d videos", len(paths))
        return paths

    # ------------------------------------------------------------------ Pexels Images

    def _pexels_photo_search(self, query: str, page: int = 1) -> list[dict]:
        resp = self.session.get(
            PEXELS_PHOTO_API,
            params={"query": query, "per_page": PEXELS_PER_PAGE, "page": page},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("photos", [])

    def fetch_images(self, keywords: list[str], count: int = 8) -> list[Path]:
        """Fetch high-res images; they'll get Ken Burns treatment in compositor."""
        paths: list[Path] = []
        used_ids: set[int] = set()

        for keyword in keywords:
            if len(paths) >= count:
                break
            try:
                photos = self._pexels_photo_search(keyword)
                for p in photos:
                    if len(paths) >= count:
                        break
                    pid = p["id"]
                    if pid in used_ids:
                        continue
                    url = p.get("src", {}).get("original") or p.get("src", {}).get("large2x")
                    if not url:
                        continue
                    dest = self.image_dir / f"{pid}.jpg"
                    if self._download(url, dest):
                        paths.append(dest)
                        used_ids.add(pid)
                time.sleep(0.3)
            except Exception as e:
                logger.warning("Pexels photo error for '%s': %s", keyword, e)

        logger.info("Fetched %d images", len(paths))
        return paths

    # ------------------------------------------------------------------ Ken Burns Prep

    def ken_burns_params(self, image_path: Path, duration: float) -> dict:
        """
        Returns zoom/pan parameters for Ken Burns effect in compositor.
        Alternates between zoom-in-left, zoom-in-right, zoom-out-center.
        """
        img = Image.open(image_path)
        w, h = img.size

        styles = ["zoom_in_left", "zoom_in_right", "zoom_out_center", "pan_right", "pan_left"]
        style = random.choice(styles)

        zoom_start = 1.0
        zoom_end = 1.0
        pan_x_start, pan_x_end = 0.5, 0.5
        pan_y_start, pan_y_end = 0.5, 0.5

        if style == "zoom_in_left":
            zoom_start, zoom_end = 1.0, 1.12
            pan_x_start, pan_x_end = 0.35, 0.45
        elif style == "zoom_in_right":
            zoom_start, zoom_end = 1.0, 1.12
            pan_x_start, pan_x_end = 0.65, 0.55
        elif style == "zoom_out_center":
            zoom_start, zoom_end = 1.15, 1.0
        elif style == "pan_right":
            zoom_start = zoom_end = 1.08
            pan_x_start, pan_x_end = 0.3, 0.7
        elif style == "pan_left":
            zoom_start = zoom_end = 1.08
            pan_x_start, pan_x_end = 0.7, 0.3

        return {
            "style": style,
            "duration": duration,
            "zoom_start": zoom_start,
            "zoom_end": zoom_end,
            "pan_x_start": pan_x_start,
            "pan_x_end": pan_x_end,
            "pan_y_start": pan_y_start,
            "pan_y_end": pan_y_end,
            "source_w": w,
            "source_h": h,
        }

    # ------------------------------------------------------------------ Keyword extraction

    @staticmethod
    def extract_keywords(topic: str, script_text: str, n: int = 8) -> list[str]:
        """Simple keyword extraction — returns topic words + common visual terms."""
        words = topic.lower().split()
        # Add cinematic search terms for better B-roll
        cinematic = ["cinematic", "documentary", "historical", "dramatic", "ancient"]
        return (words + cinematic)[:n]
