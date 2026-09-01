"""Stage 6: MoviePy Compositor — assembles video clips + Ken Burns images + subtitles."""

import logging
import math
import random
from pathlib import Path

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image

from config import (
    OUTPUT_DIR,
    SUBTITLE_FONT,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_STROKE_COLOR,
    SUBTITLE_STROKE_WIDTH,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from modules.script_engine import Script

logger = logging.getLogger(__name__)

HOOK_CUT_INTERVAL = 2.0   # seconds per clip during hook section
STORY_CUT_INTERVAL = 5.0  # seconds per clip during story sections

# Fade between clips
CROSSFADE_DURATION = 0.4


class Compositor:
    def __init__(self, topic_slug: str):
        self.slug = topic_slug
        self.out_dir = OUTPUT_DIR / topic_slug
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ Ken Burns

    def _ken_burns_clip(self, image_path: Path, duration: float) -> ImageClip:
        """Animate a still image with zoom/pan (Ken Burns effect)."""
        img = Image.open(image_path).convert("RGB")
        src_w, src_h = img.size
        target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT

        # Scale so image covers the canvas
        scale = max(target_w / src_w, target_h / src_h) * 1.15
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        img_np = np.array(img)

        # Random Ken Burns style
        styles = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
        style = random.choice(styles)
        n_frames = int(duration * VIDEO_FPS)

        def make_frame(t: float):
            progress = t / max(duration, 0.001)
            if style == "zoom_in":
                zoom = 1.0 + 0.12 * progress
            elif style == "zoom_out":
                zoom = 1.12 - 0.12 * progress
            else:
                zoom = 1.06

            frame_w = int(target_w / zoom)
            frame_h = int(target_h / zoom)

            if style == "pan_left":
                cx = int(new_w * 0.65 - new_w * 0.3 * progress)
            elif style == "pan_right":
                cx = int(new_w * 0.35 + new_w * 0.3 * progress)
            else:
                cx = new_w // 2

            cy = new_h // 2
            x1 = max(0, cx - frame_w // 2)
            y1 = max(0, cy - frame_h // 2)
            x2 = min(new_w, x1 + frame_w)
            y2 = min(new_h, y1 + frame_h)

            crop = img_np[y1:y2, x1:x2]
            # Resize crop to target
            from PIL import Image as PILImage
            crop_pil = PILImage.fromarray(crop).resize((target_w, target_h), PILImage.LANCZOS)
            return np.array(crop_pil)

        clip = ImageClip(img_np, duration=duration)
        clip = clip.fl(lambda gf, t: make_frame(t), apply_to="mask")
        # Use make_frame directly for efficiency
        from moviepy.editor import VideoClip
        kb_clip = VideoClip(make_frame, duration=duration)
        return kb_clip

    # ------------------------------------------------------------------ Clip pool

    def _build_clip_pool(
        self,
        video_paths: list[Path],
        image_paths: list[Path],
        section_type: str,
        cut_interval: float,
        total_duration: float,
    ) -> list:
        """Build a sequence of video/image clips to fill `total_duration`."""
        clips = []
        pool = list(video_paths) + list(image_paths)
        if not pool:
            bg = ColorClip((VIDEO_WIDTH, VIDEO_HEIGHT), color=(10, 10, 20), duration=cut_interval)
            pool = [None] * 20  # placeholders

        random.shuffle(pool)
        elapsed = 0.0
        pool_idx = 0

        while elapsed < total_duration:
            remaining = total_duration - elapsed
            clip_dur = min(cut_interval, remaining)
            if clip_dur < 0.1:
                break

            source = pool[pool_idx % len(pool)]
            pool_idx += 1

            try:
                if source is None:
                    clip = ColorClip((VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 15, 30), duration=clip_dur)
                elif source.suffix in (".mp4", ".mov", ".avi"):
                    vc = VideoFileClip(str(source)).without_audio()
                    # Pick a random start point
                    if vc.duration > clip_dur + 1:
                        max_start = vc.duration - clip_dur
                        start = random.uniform(0, max_start)
                        vc = vc.subclip(start, start + clip_dur)
                    else:
                        vc = vc.loop(duration=clip_dur)
                    clip = vc.resize((VIDEO_WIDTH, VIDEO_HEIGHT))
                else:  # image
                    clip = self._ken_burns_clip(source, clip_dur)
            except Exception as e:
                logger.warning("Clip load error %s: %s", source, e)
                clip = ColorClip((VIDEO_WIDTH, VIDEO_HEIGHT), color=(15, 15, 30), duration=clip_dur)

            clips.append(clip)
            elapsed += clip_dur

        return clips

    # ------------------------------------------------------------------ Subtitles

    def _build_subtitle_clips(self, word_specs: list[dict]) -> list[TextClip]:
        """Create one TextClip per word with highlight on current word."""
        subtitle_clips = []
        seen_chunks: dict[float, bool] = {}

        for spec in word_specs:
            chunk_key = spec["start"]
            if chunk_key in seen_chunks:
                continue
            seen_chunks[chunk_key] = True

            line_words = spec["chunk_words"]
            line_start = spec["start"]
            line_end = spec.get("end", spec["start"] + 0.5)
            line_text = " ".join(line_words)
            duration = max(0.1, line_end - line_start)

            try:
                txt_clip = (
                    TextClip(
                        line_text,
                        fontsize=SUBTITLE_FONT_SIZE,
                        font=SUBTITLE_FONT,
                        color="white",
                        stroke_color=SUBTITLE_STROKE_COLOR,
                        stroke_width=SUBTITLE_STROKE_WIDTH,
                        method="caption",
                        size=(VIDEO_WIDTH - 100, None),
                        align="center",
                    )
                    .set_start(line_start)
                    .set_duration(duration)
                    .set_position(("center", int(VIDEO_HEIGHT * 0.80)))
                )
                subtitle_clips.append(txt_clip)
            except Exception as e:
                logger.warning("TextClip error: %s", e)

        return subtitle_clips

    # ------------------------------------------------------------------ Master render

    def render(
        self,
        script: Script,
        audio_path: Path,
        video_paths: list[Path],
        image_paths: list[Path],
        word_timestamps: list[dict],
        section_timeline: list[dict],
    ) -> Path:
        logger.info("Starting render for: %s", self.slug)

        audio = AudioFileClip(str(audio_path))
        total_duration = audio.duration

        # Build video clips per section, respecting cut_interval per section type
        all_clips = []
        for i, section in enumerate(script.sections):
            if i >= len(section_timeline):
                break
            sec_start = section_timeline[i]["start_ms"] / 1000
            sec_end = section_timeline[i]["end_ms"] / 1000
            sec_dur = sec_end - sec_start

            cut_interval = section.cut_interval  # 2s for hook, 5s for story

            # Choose video/image pool — for hook use more dramatic clips
            vpool = video_paths
            ipool = image_paths if section.section_type == "story" else []

            seg_clips = self._build_clip_pool(vpool, ipool, section.section_type, cut_interval, sec_dur)
            if seg_clips:
                seg_video = concatenate_videoclips(seg_clips, method="compose")
                seg_video = seg_video.set_start(sec_start)
                all_clips.append(seg_video)

        if not all_clips:
            logger.warning("No visual clips built — using black background")
            all_clips = [ColorClip((VIDEO_WIDTH, VIDEO_HEIGHT), color=(0, 0, 0), duration=total_duration)]

        # Merge all clip segments into one timeline
        bg = concatenate_videoclips(all_clips, method="compose").set_duration(total_duration)

        # Word-by-word subtitles
        subtitle_clips = self._build_subtitle_clips(word_timestamps)

        # Composite
        layers = [bg] + subtitle_clips
        final = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
        final = final.set_audio(audio).set_duration(total_duration)

        out_path = self.out_dir / "final_video.mp4"
        final.write_videofile(
            str(out_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            preset="fast",
            threads=4,
            verbose=False,
            logger=None,
        )
        logger.info("Video rendered: %s", out_path)
        return out_path
