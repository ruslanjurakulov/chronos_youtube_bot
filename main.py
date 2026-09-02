#!/usr/bin/env python3
"""
Chronos YouTube Bot — Full Pipeline
  1. Topic Manager       → picks fresh viral topic
  2. Script Engine       → Gemini Hook + Story + Open Loops + SFX/Music cues
  3. Audio Mixer         → TTS multi-voice + SFX + dynamic music
  4. Media Fetcher       → Pexels HD videos + images
  5. Subtitle Generator  → Whisper word-by-word animated captions
  6. Thumbnail Generator → A/B Pillow thumbnails
  7. Compositor          → MoviePy final .mp4
  8. YouTube Uploader    → auto-upload via YouTube Data API v3
"""

import argparse
import logging
import re
import sys
from pathlib import Path

# Ensure required directories exist before any imports that may reference them
Path("logs").mkdir(exist_ok=True)
Path("history").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)

from config import OUTPUT_DIR, YOUTUBE_PRIVACY
from modules.audio_mixer import AudioMixer
from modules.compositor import Compositor
from modules.media_fetcher import MediaFetcher
from modules.script_engine import ScriptEngine
from modules.subtitle_generator import SubtitleGenerator
from modules.thumbnail_generator import ThumbnailGenerator
from modules.topic_manager import TopicManager
from modules.youtube_uploader import YouTubeUploader
from tools.generate_assets import ensure_assets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/run.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("chronos")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def run(
    niche: str = "history mysteries",
    topic: str | None = None,
    privacy: str = YOUTUBE_PRIVACY,
    skip_upload: bool = False,
    script_file: str | None = None,
):
    Path("logs").mkdir(exist_ok=True)
    logger.info("=== Chronos YouTube Bot starting ===")

    # ── Stage 0: Assets
    # SFX/music are synthesized rather than committed (17MB of WAV from 12KB of
    # code). Existing files are never overwritten, so real recordings dropped
    # into assets/ as .mp3 take precedence — see tools/generate_assets.py.
    written = ensure_assets(verbose=False)
    if written:
        logger.info("Generated %d missing audio assets", written)

    # ── Stages 1-2: Topic and Script
    # A saved script skips both Gemini calls, so a crash in a later stage — or a
    # spent daily quota — does not mean paying for generation again.
    topic_mgr = TopicManager()

    if script_file:
        script = ScriptEngine.load(Path(script_file), topic)
        topic = script.topic
        logger.info("Script loaded from %s — no API calls", script_file)
    else:
        if topic is None:
            topic = topic_mgr.pick_topic(niche)
        logger.info("Topic: %s", topic)
        script = ScriptEngine().generate(topic)

    slug = slugify(topic)
    logger.info("Script: '%s'", script.title)

    if not script_file:
        saved = script.save(OUTPUT_DIR / slug / "script.json")
        logger.info("Script saved: %s — reuse with --script-file", saved)

    # Per-section Pexels keywords — already inside the script JSON, no API call.
    keyword_map = ScriptEngine.extract_visual_keywords(script)

    # ── Stage 3: Audio
    mixer = AudioMixer(slug)
    audio_path, timeline = mixer.build(script)

    # ── Stage 4: Media
    fetcher = MediaFetcher(slug)

    # Gather all unique keywords from Gemini keyword map
    all_keywords = list({kw for entry in keyword_map for kw in entry.get("keywords", [])})
    if not all_keywords:
        all_keywords = fetcher.extract_keywords(topic)

    videos = fetcher.fetch_videos(all_keywords, count=12)
    images = fetcher.fetch_images(all_keywords, count=8)
    logger.info("Media: %d videos, %d images", len(videos), len(images))

    # ── Stage 5: Subtitles
    sub_gen = SubtitleGenerator(slug)
    word_timestamps = sub_gen.transcribe(audio_path)
    sub_gen.to_srt(word_timestamps)
    word_clips_specs = sub_gen.word_clips(word_timestamps, VIDEO_WIDTH, VIDEO_HEIGHT)

    # ── Stage 6: Thumbnails
    bg_a = images[0] if images else None
    bg_b = images[1] if len(images) > 1 else None
    thumb_gen = ThumbnailGenerator(slug)
    thumb_a, thumb_b = thumb_gen.generate(
        topic=script.topic,
        overlay_text=script.thumbnail_overlay_text or "SHOCKING",
        background_a=bg_a,
        background_b=bg_b,
    )
    logger.info("Thumbnails: %s | %s", thumb_a.name, thumb_b.name)

    # ── Stage 7: Compositor
    comp = Compositor(slug)
    video_path = comp.render(
        script=script,
        audio_path=audio_path,
        video_paths=videos,
        image_paths=images,
        word_timestamps=word_clips_specs,
        section_timeline=timeline,
    )
    logger.info("Video: %s", video_path)

    # ── Stage 8: Upload
    # The video is already on disk by this point, so no upload failure may cost
    # us the topic registration — otherwise a bad channel ID or an expired token
    # means the same topic gets picked again next run despite the finished file.
    if not skip_upload:
        try:
            uploader = YouTubeUploader()
            url = uploader.upload(video_path, script, thumbnail_path=thumb_a, privacy=privacy)
            logger.info("YouTube URL: %s", url)
            print(f"\n✓ Published: {url}")
        except Exception as e:
            logger.error("YouTube upload failed (%s): %s", type(e).__name__, e)
            print(f"\n✓ Video saved, upload failed: {video_path}")
    else:
        print(f"\n✓ Video saved (upload skipped): {video_path}")

    topic_mgr.register_topic(topic, video_path)

    logger.info("=== Done ===")
    return video_path


def list_channels():
    """Prints all YouTube channels for the authenticated account."""
    uploader = YouTubeUploader()
    channels = uploader.list_channels()
    if not channels:
        print("Hech qanday kanal topilmadi.")
        return
    print("\nSizning YouTube kanallaringiz:")
    print("-" * 60)
    for ch in channels:
        print(f"  ID   : {ch['id']}")
        print(f"  Nom  : {ch['name']}")
        print(f"  URL  : {ch['url']}")
        print("-" * 60)
    print("\nKerakli kanal ID sini .env fayliga qo'ying:")
    print("  YOUTUBE_CHANNEL_ID=UC...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chronos YouTube Bot")
    parser.add_argument("--niche", default="history mysteries", help="Video niche/topic area")
    parser.add_argument("--topic", default=None, help="Override topic manually")
    parser.add_argument("--privacy", default=YOUTUBE_PRIVACY, choices=["private", "unlisted", "public"])
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--list-channels", action="store_true", help="Show all YouTube channels and exit")
    parser.add_argument("--script-file", default=None,
                        help="Reuse a saved script JSON instead of calling Gemini "
                             "(e.g. output/<slug>/script.json, or samples/demo_script.json)")
    args = parser.parse_args()

    if args.list_channels:
        list_channels()
    else:
        run(
            niche=args.niche,
            topic=args.topic,
            privacy=args.privacy,
            skip_upload=args.no_upload,
            script_file=args.script_file,
        )
