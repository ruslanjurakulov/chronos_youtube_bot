"""Stage 2: Gemini Script Engine — 3-sec Hook + Open Loops + Pauses + Multi-Voice + SFX Cues."""

import json
import logging
import re
from dataclasses import dataclass, field

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL, SCRIPT_LANGUAGE, VIDEO_DURATION_TARGET

logger = logging.getLogger(__name__)

SCRIPT_SYSTEM_PROMPT = """
You are an elite viral YouTube scriptwriter. Your scripts follow strict retention psychology rules:

HOOK RULE: Never start from the beginning. Start from the CLIMAX — the most shocking/mysterious moment.
Example bad hook: "In the 18th century, there was an event..."
Example GREAT hook: "They found Europe's biggest treasure — and within 5 minutes, it sank forever..."

OPEN LOOPS: Plant 2-3 questions that you answer only at the end. Example:
"But who hid the treasure? We'll get to that at the very end..."

PAUSES: Mark dramatic pauses with [PAUSE:1.5] (number = seconds of silence). Use after shocking reveals.

MULTI-VOICE: Main narrator uses [VOICE:main]. For quotes, mysterious facts, or character speech use [VOICE:secondary].
Example: [VOICE:secondary] "I will never reveal the secret," he whispered.

SFX CUES: Inline [SFX:sound_name] — available sounds:
  whoosh, deep_boom, paper_turn, dramatic_sting, thunder_crack, heartbeat,
  clock_tick, suspense_riser, glass_shatter, choir_hit, eerie_wind, fire_crackle

MUSIC CUES: [MUSIC:intro_high] at start, [MUSIC:story_low] during narrative, [MUSIC:climax_high] at peak moments.

STRUCTURE RULE: The script MUST have exactly 2 top-level parts:
  PART 1 — "hook" section (type: "hook", duration 0-15 seconds): Start from the CLIMAX.
    Shock the viewer. No context yet. Make them desperately want to know what happened.
  PART 2 — "main_story" sections (type: "story"): Chronological, detailed narrative.
    Each section ~45-60 seconds. This is where you answer the open loops.

Return a JSON object with this EXACT schema:
{
  "title": "YouTube title — start with number or power word, max 80 chars",
  "title_ab": "Alternative A/B test title",
  "description": "YouTube description: 3 paragraphs + timestamps + hashtags",
  "tags": ["tag1", "tag2"],
  "hook_sentence": "The 3-second hook sentence (from the climax)",
  "thumbnail_prompt_a": "Thumbnail A: dramatic scene, person with shocked expression, dark cinematic",
  "thumbnail_prompt_b": "Thumbnail B: different angle/color, text overlay idea",
  "thumbnail_overlay_text": "Short shock text for thumbnail (max 4 words, e.g. NEVER OPENED!)",
  "open_loops": ["loop question 1", "loop question 2"],
  "sections": [
    {
      "name": "hook",
      "type": "hook",
      "voice": "main",
      "narration": "[MUSIC:intro_high] [SFX:dramatic_sting] They found Europe's biggest treasure... [PAUSE:1.5] and within 5 minutes, [SFX:deep_boom] it sank forever. [PAUSE:1.0] But HOW? [PAUSE:0.5] And who is responsible?",
      "duration_hint": 15,
      "cut_interval": 2
    },
    {
      "name": "open_loop_plant",
      "type": "story",
      "voice": "main",
      "narration": "[MUSIC:story_low] Let me take you back to 1715... [PAUSE:1.0] But first — who was the man behind all of this? We'll reveal that at the very end.",
      "duration_hint": 20,
      "cut_interval": 5
    }
  ]
}
"""


@dataclass
class ScriptSection:
    name: str
    narration: str
    duration_hint: int
    voice: str = "main"
    section_type: str = "story"   # "hook" | "story"
    cut_interval: float = 5.0     # seconds between video cuts (2s for hook, 5s for story)
    sfx_cues: list[dict] = field(default_factory=list)
    music_cues: list[dict] = field(default_factory=list)
    pauses: list[dict] = field(default_factory=list)

    def clean_narration(self) -> str:
        """Strip all cue tags, return plain TTS-ready text."""
        text = self.narration
        text = re.sub(r"\[SFX:[^\]]+\]", "", text)
        text = re.sub(r"\[MUSIC:[^\]]+\]", "", text)
        text = re.sub(r"\[PAUSE:[^\]]+\]", "", text)
        text = re.sub(r"\[VOICE:[^\]]+\]", "", text)
        return re.sub(r" {2,}", " ", text).strip()

    def tts_segments(self) -> list[dict]:
        """Split narration by [VOICE:X] tags into segments with voice labels."""
        segments = []
        pattern = r"(\[VOICE:(\w+)\])"
        parts = re.split(pattern, self.narration)
        current_voice = self.voice
        buffer = ""
        i = 0
        while i < len(parts):
            part = parts[i]
            if re.match(r"\[VOICE:\w+\]", part):
                if buffer.strip():
                    segments.append({"voice": current_voice, "text": _strip_cues(buffer)})
                    buffer = ""
                current_voice = parts[i + 1] if i + 1 < len(parts) else current_voice
                i += 2
            else:
                buffer += part
                i += 1
        if buffer.strip():
            segments.append({"voice": current_voice, "text": _strip_cues(buffer)})
        return segments

    def extract_pauses(self) -> list[dict]:
        pauses = []
        for m in re.finditer(r"\[PAUSE:([\d.]+)\]", self.narration):
            pauses.append({"duration": float(m.group(1)), "char_pos": m.start()})
        return pauses

    def extract_sfx(self) -> list[dict]:
        return [
            {"name": m.group(1).strip(), "char_pos": m.start()}
            for m in re.finditer(r"\[SFX:([^\]]+)\]", self.narration)
        ]

    def extract_music(self) -> list[dict]:
        return [
            {"cue": m.group(1).strip(), "char_pos": m.start()}
            for m in re.finditer(r"\[MUSIC:([^\]]+)\]", self.narration)
        ]


def _strip_cues(text: str) -> str:
    text = re.sub(r"\[SFX:[^\]]+\]", "", text)
    text = re.sub(r"\[MUSIC:[^\]]+\]", "", text)
    text = re.sub(r"\[PAUSE:[^\]]+\]", "", text)
    text = re.sub(r"\[VOICE:[^\]]+\]", "", text)
    return re.sub(r" {2,}", " ", text).strip()


@dataclass
class Script:
    topic: str
    title: str
    title_ab: str
    description: str
    tags: list[str]
    hook_sentence: str
    sections: list[ScriptSection]
    thumbnail_prompt_a: str
    thumbnail_prompt_b: str
    thumbnail_overlay_text: str
    open_loops: list[str]

    def full_narration(self) -> str:
        return "\n\n".join(s.clean_narration() for s in self.sections)

    def all_sfx_cues(self) -> list[dict]:
        return [cue for s in self.sections for cue in s.extract_sfx()]

    def all_music_cues(self) -> list[dict]:
        return [cue for s in self.sections for cue in s.extract_music()]


class ScriptEngine:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=SCRIPT_SYSTEM_PROMPT,
        )

    def generate(self, topic: str) -> Script:
        prompt = (
            f"Topic: {topic}\n"
            f"Language: {SCRIPT_LANGUAGE}\n"
            f"Target duration: {VIDEO_DURATION_TARGET} seconds\n\n"
            "Write the full viral YouTube script JSON now. "
            "Include at least 6 sections, 2 open loops, and multiple [PAUSE], [SFX], [MUSIC] cues."
        )
        logger.info("Generating script for: %s", topic)
        response = self.model.generate_content(prompt)
        raw = self._extract_json(response.text)
        return self._parse(topic, raw)

    def _extract_json(self, text: str) -> dict:
        text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]+\}", text)
            if match:
                return json.loads(match.group())
            raise ValueError("Gemini did not return valid JSON") from None

    def extract_visual_keywords(self, script: "Script") -> list[dict]:
        """Ask Gemini to suggest Pexels search keywords per section."""
        sections_text = "\n".join(
            f"[{s.name}]: {s.clean_narration()[:300]}" for s in script.sections
        )
        prompt = (
            "You are a video editor selecting B-roll footage keywords.\n"
            f"For each script section below, provide 2-3 Pexels search keywords "
            f"(cinematic, dramatic, matching the mood).\n\n{sections_text}\n\n"
            "Return JSON: [{\"section\": \"name\", \"keywords\": [\"kw1\", \"kw2\"]}]"
        )
        resp = self.model.generate_content(prompt)
        try:
            raw = self._extract_json(resp.text)
            if isinstance(raw, list):
                return raw
        except Exception:
            pass
        # Fallback: use topic words
        words = script.topic.lower().split()
        return [{"section": s.name, "keywords": words[:2]} for s in script.sections]

    def _parse(self, topic: str, data: dict) -> Script:
        sections = []
        for i, s in enumerate(data.get("sections", [])):
            sec = ScriptSection(
                name=s.get("name", f"section_{i}"),
                narration=s.get("narration", ""),
                duration_hint=int(s.get("duration_hint", 45)),
                voice=s.get("voice", "main"),
                section_type=s.get("type", "hook" if i == 0 else "story"),
                cut_interval=float(s.get("cut_interval", 2.0 if i == 0 else 5.0)),
            )
            sec.sfx_cues = sec.extract_sfx()
            sec.music_cues = sec.extract_music()
            sec.pauses = sec.extract_pauses()
            sections.append(sec)

        return Script(
            topic=topic,
            title=data.get("title", topic),
            title_ab=data.get("title_ab", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            hook_sentence=data.get("hook_sentence", data.get("hook", "")),
            sections=sections,
            thumbnail_prompt_a=data.get("thumbnail_prompt_a", ""),
            thumbnail_prompt_b=data.get("thumbnail_prompt_b", ""),
            thumbnail_overlay_text=data.get("thumbnail_overlay_text", ""),
            open_loops=data.get("open_loops", []),
        )
