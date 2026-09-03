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
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Ensure required directories exist before any imports that may reference them
Path("logs").mkdir(exist_ok=True)
Path("history").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)

from config import OUTPUT_DIR, VIDEO_HEIGHT, VIDEO_WIDTH, YOUTUBE_CATEGORY_ID, YOUTUBE_PRIVACY
from modules import event_log as events
from modules.audio_mixer import AudioMixer
from modules.claim_extractor import extract_claims
from modules.compositor import Compositor
from modules.fact_checker import fact_check_claims
from modules.media_fetcher import MediaFetcher
from modules.pipeline_stages import PipelineStage, PipelineStateMachine
from modules.research_engine import research_topic
from modules.script_engine import ScriptEngine
from modules.state_store import StateStore
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
    # Observability events (event_log.emit never raises and never alters the
    # pipeline — see modules/event_log.py). They feed the Command Center's live
    # activity feed and per-video pipeline timeline.
    events.emit(events.SYSTEM_STARTED, agent="pipeline", status=events.STATUS_RUNNING)

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
    events.emit(events.TOPIC_SELECTED, agent="topic_manager", status=events.STATUS_COMPLETED, metadata={"topic": topic})

    # ── Pipeline stage tracking (audit trail only — does NOT gate publish)
    # This run is tracked through Topic -> Research -> Script -> Fact Check ->
    # Human Approval so the record is honest about what actually happened at
    # each stage. It deliberately stops at Human Approval: approve() is never
    # called here, so the run never reaches Publish through this mechanism.
    # Upload below proceeds exactly as before, independent of this state —
    # wiring an actual approval requirement is a deliberate follow-up decision,
    # not something this pipeline enforces yet.
    pipeline = PipelineStateMachine()
    run_record = pipeline.start_run(topic)

    research_brief = None
    if script_file:
        pipeline.advance(run_record.run_id, PipelineStage.RESEARCH, note="skipped — script loaded from file")
    else:
        pipeline.advance(run_record.run_id, PipelineStage.RESEARCH)
        events.emit(events.RESEARCH_STARTED, agent="research_engine", status=events.STATUS_RUNNING, metadata={"topic": topic})
        try:
            research_brief = research_topic(topic, niche)
            logger.info("Research: %d fact(s), %d open question(s)",
                        len(research_brief.key_facts), len(research_brief.open_questions))
            events.emit(events.RESEARCH_COMPLETED, agent="research_engine", status=events.STATUS_COMPLETED,
                        metadata={"facts": len(research_brief.key_facts), "open_questions": len(research_brief.open_questions)})
        except Exception as e:
            logger.warning("Research engine failed (%s: %s) — generating script without research notes",
                            type(e).__name__, e)
            events.emit(events.AGENT_FAILED, agent="research_engine", status=events.STATUS_FAILED,
                        metadata={"error": f"{type(e).__name__}: {e}"})

    if not script_file:
        events.emit(events.SCRIPT_STARTED, agent="script_engine", status=events.STATUS_RUNNING, metadata={"topic": topic})
        script = ScriptEngine().generate(topic, research_brief=research_brief)

    slug = slugify(topic)
    logger.info("Script: '%s'", script.title)
    events.emit(events.SCRIPT_COMPLETED, agent="script_engine", status=events.STATUS_COMPLETED, metadata={"title": script.title})
    pipeline.advance(run_record.run_id, PipelineStage.SCRIPT)

    if not script_file:
        saved = script.save(OUTPUT_DIR / slug / "script.json")
        logger.info("Script saved: %s — reuse with --script-file", saved)

    # ── Fact-check pass (advisory only — see modules/fact_checker.py)
    # Flags claims for human review; never blocks generation or upload itself.
    pipeline.advance(run_record.run_id, PipelineStage.FACT_CHECK)
    try:
        claims = extract_claims(script)
        fact_results = fact_check_claims(claims) if claims else []
        flagged = [r for r in fact_results if r.requires_human_review]
        if flagged:
            logger.warning("Fact-check: %d/%d claim(s) flagged for human review", len(flagged), len(fact_results))
        else:
            logger.info("Fact-check: %d claim(s) checked, none flagged", len(fact_results))
        if fact_results:
            fc_path = OUTPUT_DIR / slug / "fact_check.json"
            fc_path.parent.mkdir(parents=True, exist_ok=True)
            fc_path.write_text(json.dumps([r.__dict__ for r in fact_results], indent=2, ensure_ascii=False))
            logger.info("Fact-check results saved: %s", fc_path)
    except Exception as e:
        logger.warning("Fact-checker failed (%s: %s) — proceeding without fact-check results",
                        type(e).__name__, e)

    pipeline.advance(run_record.run_id, PipelineStage.HUMAN_APPROVAL)

    # Per-section Pexels keywords — already inside the script JSON, no API call.
    keyword_map = ScriptEngine.extract_visual_keywords(script)

    # ── Stage 3: Audio
    events.emit(events.VOICE_STARTED, agent="audio_mixer", status=events.STATUS_RUNNING)
    mixer = AudioMixer(slug)
    audio_path, timeline = mixer.build(script)
    events.emit(events.VOICE_COMPLETED, agent="audio_mixer", status=events.STATUS_COMPLETED)

    # ── Stage 4: Media
    events.emit(events.MEDIA_STARTED, agent="media_fetcher", status=events.STATUS_RUNNING)
    fetcher = MediaFetcher(slug)

    # Gather all unique keywords from Gemini keyword map
    all_keywords = list({kw for entry in keyword_map for kw in entry.get("keywords", [])})
    if not all_keywords:
        all_keywords = fetcher.extract_keywords(topic)

    videos = fetcher.fetch_videos(all_keywords, count=12)
    images = fetcher.fetch_images(all_keywords, count=8)
    logger.info("Media: %d videos, %d images", len(videos), len(images))
    events.emit(events.MEDIA_COMPLETED, agent="media_fetcher", status=events.STATUS_COMPLETED,
                metadata={"videos": len(videos), "images": len(images)})

    # ── Stage 5: Subtitles
    sub_gen = SubtitleGenerator(slug)
    word_timestamps = sub_gen.transcribe(audio_path)
    sub_gen.to_srt(word_timestamps)
    word_clips_specs = sub_gen.word_clips(word_timestamps, VIDEO_WIDTH, VIDEO_HEIGHT)

    # ── Stage 6: Thumbnails
    events.emit(events.THUMBNAIL_STARTED, agent="thumbnail_generator", status=events.STATUS_RUNNING)
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
    events.emit(events.THUMBNAIL_COMPLETED, agent="thumbnail_generator", status=events.STATUS_COMPLETED)

    # ── Stage 7: Compositor
    events.emit(events.RENDER_STARTED, agent="compositor", status=events.STATUS_RUNNING)
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
    events.emit(events.RENDER_COMPLETED, agent="compositor", status=events.STATUS_COMPLETED,
                metadata={"video_path": str(video_path)})

    # ── Stage 8: Upload
    # The video is already on disk by this point, so no upload failure may cost
    # us the topic registration — otherwise a bad channel ID or an expired token
    # means the same topic gets picked again next run despite the finished file.
    video_id, video_url = None, None
    if not skip_upload:
        events.emit(events.UPLOAD_STARTED, agent="youtube_uploader", status=events.STATUS_RUNNING, metadata={"topic": topic})
        try:
            uploader = YouTubeUploader()
            uploaded = uploader.upload(video_path, script, thumbnail_path=thumb_a, privacy=privacy)
            video_id, video_url = uploaded["id"], uploaded["url"]
            logger.info("YouTube URL: %s", video_url)
            print(f"\n✓ Published: {video_url}")
            with StateStore() as store:
                store.record_video(
                    video_id=video_id,
                    topic=topic,
                    title=script.title,
                    slug=slug,
                    published_at=datetime.utcnow().isoformat(),
                    privacy=privacy,
                    category_id=YOUTUBE_CATEGORY_ID,
                    local_path=str(video_path),
                )
                events.emit(events.UPLOAD_COMPLETED, video_id=video_id, agent="youtube_uploader",
                            status=events.STATUS_COMPLETED, metadata={"url": video_url}, store=store)
                events.emit(events.VIDEO_PUBLISHED, video_id=video_id, agent="youtube_uploader",
                            status=events.STATUS_COMPLETED, metadata={"title": script.title, "url": video_url, "privacy": privacy}, store=store)
        except Exception as e:
            logger.error("YouTube upload failed (%s): %s", type(e).__name__, e)
            print(f"\n✓ Video saved, upload failed: {video_path}")
            events.emit(events.UPLOAD_FAILED, agent="youtube_uploader", status=events.STATUS_FAILED,
                        metadata={"error": f"{type(e).__name__}: {e}"})
    else:
        print(f"\n✓ Video saved (upload skipped): {video_path}")

    topic_mgr.register_topic(topic, video_path, video_id=video_id, video_url=video_url)

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
