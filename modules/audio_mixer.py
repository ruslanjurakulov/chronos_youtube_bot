"""Stage 3: TTS & Audio Mixer — Multi-voice narration + SFX + Dynamic music."""

import asyncio
import logging
import os
from pathlib import Path

import edge_tts
from pydub import AudioSegment
from pydub.effects import normalize

from config import (
    EDGE_TTS_VOICE,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    MUSIC_DIR,
    MUSIC_VOLUME,
    NARRATOR_VOLUME,
    OUTPUT_DIR,
    SFX_DIR,
    SFX_VOLUME,
    TTS_PROVIDER,
)
from modules.script_engine import Script, ScriptSection

logger = logging.getLogger(__name__)

# Secondary (mysterious/deep) voice for quotes
EDGE_TTS_SECONDARY_VOICE = "en-US-GuyNeural"

# Music cue → volume dB mapping (applied as volume reduction from 0 dB base)
MUSIC_VOLUME_MAP = {
    "intro_high": -8,   # loud, energetic
    "story_low": -22,   # quiet background
    "climax_high": -6,  # loudest
    "outro": -14,
}

# Pattern-interrupt interval: add a subtle audio trigger every N seconds
PATTERN_INTERRUPT_INTERVAL = 35  # seconds


class AudioMixer:
    def __init__(self, topic_slug: str):
        self.slug = topic_slug
        self.work_dir = OUTPUT_DIR / topic_slug / "audio"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ TTS

    async def _tts_edge(self, text: str, voice: str, out_path: Path):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    def _tts_elevenlabs(self, text: str, voice_id: str, out_path: Path):
        from elevenlabs import ElevenLabs, VoiceSettings  # lazy import

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(stability=0.45, similarity_boost=0.82),
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

    def _render_segment(self, text: str, voice_role: str, idx: int) -> Path:
        """Render a single TTS segment, return path to .mp3."""
        out = self.work_dir / f"seg_{idx:04d}_{voice_role}.mp3"
        if out.exists():
            return out
        if TTS_PROVIDER == "elevenlabs":
            vid = ELEVENLABS_VOICE_ID if voice_role == "main" else "D38z5RcWu1voky8WS1ja"
            self._tts_elevenlabs(text, vid, out)
        else:
            voice = EDGE_TTS_VOICE if voice_role == "main" else EDGE_TTS_SECONDARY_VOICE
            asyncio.run(self._tts_edge(text, voice, out))
        return out

    def render_narration(self, script: Script) -> tuple[AudioSegment, list[dict]]:
        """
        Returns (full_narration_audio, word_timestamps_list).
        word_timestamps are approximate — exact ones come from Whisper later.
        Inserts [PAUSE] silences between segments.
        """
        combined = AudioSegment.empty()
        timeline = []  # [{start_ms, end_ms, section_name}]
        seg_idx = 0

        for section in script.sections:
            segments = section.tts_segments()
            pauses = section.pauses

            # Build narration with pauses inserted
            section_audio = AudioSegment.empty()
            pause_positions = {p["char_pos"]: p["duration"] for p in pauses}

            for seg in segments:
                if not seg["text"].strip():
                    continue
                path = self._render_segment(seg["text"], seg["voice"], seg_idx)
                seg_idx += 1
                part = AudioSegment.from_file(path)
                part = normalize(part) + (20 * (NARRATOR_VOLUME - 1))
                section_audio += part

            # Append pause after section if specified (crude: insert at end)
            section_total_pause_ms = int(sum(p["duration"] for p in pauses) * 1000)
            if section_total_pause_ms:
                section_audio += AudioSegment.silent(duration=section_total_pause_ms)

            start_ms = len(combined)
            combined += section_audio
            timeline.append({
                "section": section.name,
                "start_ms": start_ms,
                "end_ms": len(combined),
            })
            logger.debug("Section '%s': %.1fs", section.name, len(section_audio) / 1000)

        narration_path = self.work_dir / "narration.mp3"
        combined.export(narration_path, format="mp3", bitrate="192k")
        logger.info("Narration rendered: %.1fs", len(combined) / 1000)
        return combined, timeline

    # ------------------------------------------------------------------ SFX

    def _load_sfx(self, name: str) -> AudioSegment | None:
        for ext in ("mp3", "wav", "ogg"):
            path = SFX_DIR / f"{name}.{ext}"
            if path.exists():
                return AudioSegment.from_file(path)
        logger.warning("SFX not found: %s", name)
        return None

    def mix_sfx(self, base: AudioSegment, timeline: list[dict], script: Script) -> AudioSegment:
        """Overlay SFX cues onto base audio at approximate positions."""
        result = base
        total_ms = len(base)

        # Collect all sfx with absolute time estimates
        all_cues = []
        for i, section in enumerate(script.sections):
            if i >= len(timeline):
                break
            sec_start = timeline[i]["start_ms"]
            sec_end = timeline[i]["end_ms"]
            sec_dur = sec_end - sec_start
            narration_len = max(len(section.narration), 1)

            for cue in section.sfx_cues:
                rel = cue["char_pos"] / narration_len
                abs_ms = int(sec_start + rel * sec_dur)
                all_cues.append({"name": cue["name"], "ms": abs_ms})

        for cue in all_cues:
            sfx = self._load_sfx(cue["name"])
            if sfx is None:
                continue
            sfx = sfx + (20 * (SFX_VOLUME - 1))
            pos = min(cue["ms"], total_ms - 100)
            result = result.overlay(sfx, position=pos)
            logger.debug("SFX '%s' at %.1fs", cue["name"], pos / 1000)

        return result

    # ------------------------------------------------------------------ Music

    def _load_music(self, cue: str) -> AudioSegment | None:
        for ext in ("mp3", "wav"):
            path = MUSIC_DIR / f"{cue}.{ext}"
            if path.exists():
                return AudioSegment.from_file(path)
        # fallback: any music file
        files = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
        if files:
            return AudioSegment.from_file(files[0])
        logger.warning("No music file found for cue: %s", cue)
        return None

    def mix_music(self, base: AudioSegment, timeline: list[dict], script: Script) -> AudioSegment:
        """Build a dynamic music layer that changes volume per cue, overlay onto base."""
        total_ms = len(base)
        music_layer = AudioSegment.silent(duration=total_ms)

        # Resolve music cue times
        cue_times = []
        for i, section in enumerate(script.sections):
            if i >= len(timeline):
                break
            sec_start = timeline[i]["start_ms"]
            sec_dur = timeline[i]["end_ms"] - sec_start
            narration_len = max(len(section.narration), 1)
            for mc in section.music_cues:
                rel = mc["char_pos"] / narration_len
                abs_ms = int(sec_start + rel * sec_dur)
                cue_times.append({"cue": mc["cue"], "ms": abs_ms})

        # Default: intro_high → story_low if no explicit cues
        if not cue_times:
            cue_times = [
                {"cue": "intro_high", "ms": 0},
                {"cue": "story_low", "ms": 8000},
            ]

        cue_times.sort(key=lambda x: x["ms"])

        # Load a music track and build the layer segment by segment
        base_music = self._load_music(cue_times[0]["cue"])
        if base_music is None:
            return base

        # Loop music to fill total duration
        loops = (total_ms // len(base_music)) + 2
        looped = base_music * loops
        looped = looped[:total_ms]

        # Apply volume changes at cue boundaries
        result_music = AudioSegment.empty()
        prev_ms = 0
        for ct in cue_times:
            db = MUSIC_VOLUME_MAP.get(ct["cue"], -18)
            segment = looped[prev_ms:ct["ms"]] + db
            result_music += segment
            prev_ms = ct["ms"]

        # Final segment with last cue's volume
        last_db = MUSIC_VOLUME_MAP.get(cue_times[-1]["cue"], -18)
        result_music += looped[prev_ms:] + last_db

        result_music = result_music[:total_ms]
        return base.overlay(result_music)

    # ------------------------------------------------------------------ Pattern Interrupt

    def add_pattern_interrupts(self, audio: AudioSegment) -> AudioSegment:
        """Every ~35s inject a subtle whoosh to keep subconscious attention."""
        whoosh = self._load_sfx("whoosh")
        if whoosh is None:
            return audio
        whoosh_soft = whoosh - 8  # quieter
        result = audio
        pos = PATTERN_INTERRUPT_INTERVAL * 1000
        while pos < len(audio) - 2000:
            result = result.overlay(whoosh_soft, position=int(pos))
            pos += PATTERN_INTERRUPT_INTERVAL * 1000
        return result

    # ------------------------------------------------------------------ Master

    def build(self, script: Script) -> tuple[Path, list[dict]]:
        """Full pipeline: render → mix sfx → mix music → pattern interrupts → export."""
        logger.info("Building audio for topic: %s", self.slug)

        narration, timeline = self.render_narration(script)
        mixed = self.mix_sfx(narration, timeline, script)
        mixed = self.mix_music(mixed, timeline, script)
        mixed = self.add_pattern_interrupts(mixed)

        out = self.work_dir / "final_audio.mp3"
        mixed.export(out, format="mp3", bitrate="192k")
        logger.info("Final audio: %s (%.1fs)", out, len(mixed) / 1000)
        return out, timeline
