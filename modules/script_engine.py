"""Stage 2: Gemini Script Engine — 3-sec Hook + Open Loops + Pauses + Multi-Voice + SFX Cues."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from google.genai import types as genai_types

from config import GEMINI_MODEL, SCRIPT_LANGUAGE, VIDEO_DURATION_TARGET
from modules.gemini_client import generate_with_retry, make_client

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
      "cut_interval": 2,
      "keywords": ["sunken treasure ship", "stormy ocean night"]
    },
    {
      "name": "open_loop_plant",
      "type": "story",
      "voice": "main",
      "narration": "[MUSIC:story_low] Let me take you back to 1715... [PAUSE:1.0] But first — who was the man behind all of this? We'll reveal that at the very end.",
      "duration_hint": 20,
      "cut_interval": 5,
      "keywords": ["old sailing ship", "antique map candlelight"]
    }
  ]
}

KEYWORDS RULE: Every section MUST include 2-3 "keywords" — literal, filmable
stock-footage search terms for Pexels that match that section's mood. Describe
what the CAMERA SEES, not the idea: "storm waves lighthouse" not "mystery".
Avoid proper nouns and dates — stock libraries have no footage of them.
"""


@dataclass
class ScriptSection:
    name: str
    narration: str
    duration_hint: int
    voice: str = "main"
    section_type: str = "story"   # "hook" | "story"
    cut_interval: float = 5.0     # seconds between video cuts (2s for hook, 5s for story)
    keywords: list[str] = field(default_factory=list)  # Pexels search terms
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

    def tts_timeline(self) -> list[dict]:
        """Speech and silence events in written order.

        tts_segments() splits on [VOICE:] only, which loses where each [PAUSE:n]
        sat — the mixer could then do nothing better than pile every pause at the
        end of the section. This keeps them in place, so a pause after a reveal
        lands after that reveal.

        Events are {"kind": "speech", "voice": str, "text": str}
                or {"kind": "pause", "duration": float}.
        """
        events: list[dict] = []
        voice = self.voice
        buffer = ""
        pos = 0

        def flush():
            nonlocal buffer
            text = _strip_cues(buffer)
            if text:
                events.append({"kind": "speech", "voice": voice, "text": text})
            buffer = ""

        marker = re.compile(r"\[VOICE:(\w+)\]|\[PAUSE:([\d.]+)\]")
        for m in marker.finditer(self.narration):
            buffer += self.narration[pos:m.start()]
            pos = m.end()
            flush()
            if m.group(1) is not None:
                voice = m.group(1)
            else:
                events.append({"kind": "pause", "duration": float(m.group(2))})

        buffer += self.narration[pos:]
        flush()
        return events

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

    def to_dict(self) -> dict:
        """Serialize back to the same JSON shape ScriptEngine._parse consumes."""
        return {
            "topic": self.topic,
            "title": self.title,
            "title_ab": self.title_ab,
            "description": self.description,
            "tags": self.tags,
            "hook_sentence": self.hook_sentence,
            "thumbnail_prompt_a": self.thumbnail_prompt_a,
            "thumbnail_prompt_b": self.thumbnail_prompt_b,
            "thumbnail_overlay_text": self.thumbnail_overlay_text,
            "open_loops": self.open_loops,
            "sections": [
                {
                    "name": s.name,
                    "type": s.section_type,
                    "voice": s.voice,
                    "narration": s.narration,
                    "duration_hint": s.duration_hint,
                    "cut_interval": s.cut_interval,
                    "keywords": s.keywords,
                }
                for s in self.sections
            ],
        }

    def save(self, path: Path) -> Path:
        """Write to disk so a re-run can skip the paid generation step."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return path


class ScriptEngine:
    def __init__(self):
        self.client = make_client()

    @staticmethod
    def load(path: Path, topic: str | None = None) -> Script:
        """Rebuild a Script from a saved JSON file — no API call, no quota spent.

        Lets stages 3-7 be exercised without paying for generation again, which
        matters when a later stage crashes or the daily quota is gone.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return ScriptEngine._parse(topic or data.get("topic", "untitled"), data)

    def _gen(self, prompt: str, system: str | None = None) -> str:
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
        ) if system else None
        response = generate_with_retry(self.client, GEMINI_MODEL, prompt, config)
        return response.text

    def generate(self, topic: str) -> Script:
        prompt = (
            f"Topic: {topic}\n"
            f"Language: {SCRIPT_LANGUAGE}\n"
            f"Target duration: {VIDEO_DURATION_TARGET} seconds\n\n"
            "Write the full viral YouTube script JSON now. "
            "Include at least 6 sections, 2 open loops, and multiple [PAUSE], [SFX], [MUSIC] cues."
        )
        logger.info("Generating script for: %s", topic)
        text = self._gen(prompt, system=SCRIPT_SYSTEM_PROMPT)
        raw = self._extract_json(text)
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

    @staticmethod
    def extract_visual_keywords(script: "Script") -> list[dict]:
        """Per-section Pexels search keywords.

        These come back inside the script JSON itself (see KEYWORDS RULE in the
        system prompt), so this costs no extra API call — it used to be a second
        round-trip, which mattered on the free tier's 20 requests/day.
        Sections where Gemini omitted keywords fall back to the topic words.
        """
        fallback = [w for w in script.topic.lower().split() if len(w) > 3][:2]
        return [
            {"section": s.name, "keywords": s.keywords or fallback}
            for s in script.sections
        ]

    @staticmethod
    def _parse(topic: str, data: dict) -> Script:
        sections = []
        for i, s in enumerate(data.get("sections", [])):
            sec = ScriptSection(
                name=s.get("name", f"section_{i}"),
                narration=s.get("narration", ""),
                duration_hint=int(s.get("duration_hint", 45)),
                voice=s.get("voice", "main"),
                section_type=s.get("type", "hook" if i == 0 else "story"),
                cut_interval=float(s.get("cut_interval", 2.0 if i == 0 else 5.0)),
                keywords=[str(k).strip() for k in (s.get("keywords") or []) if str(k).strip()],
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
