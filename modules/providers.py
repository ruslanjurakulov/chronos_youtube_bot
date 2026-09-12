"""Provider interfaces — the seam that keeps Nightshift free of vendor lock-in.

Each capability the pipeline depends on (research, images, video clips, voice,
publishing, analytics) is expressed here as a small ``typing.Protocol``. The
concrete modules that exist today satisfy these shapes, and a future provider
(a different stock library, a different TTS, a different platform) only has to
match the shape to drop in — nothing in the pipeline needs to name the vendor.

Design notes
------------
* These are **structural** contracts (``@runtime_checkable`` Protocols), not a
  base class anyone must inherit. ``MediaFetcher`` already *is* an
  ``ImageProvider`` and a ``VideoProvider`` because it has the right methods —
  no adapter, no edit to that module. That is the point of using Protocols:
  the abstraction is additive and imposes nothing on the code it describes.
* This module holds NO API keys and makes NO network calls. It is types plus
  one thin real adapter (``GeminiResearchProvider``) around the existing
  ``research_topic`` function, whose only job is to give a module-level
  function a class shape that satisfies ``ResearchProvider``.
* Concrete adapters for voice / publishing / analytics are intentionally NOT
  written yet: ``AudioMixer``, ``YouTubeUploader`` and ``AnalyticsClient``
  carry richer constructors, and wrapping them faithfully is a follow-up. The
  contracts are defined here so that work has a target to hit.

Nothing here changes runtime behaviour; the pipeline keeps calling the concrete
modules directly until call sites are migrated behind these interfaces in a
later change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class ResearchProvider(Protocol):
    """Turns a topic into a research brief (facts, angles, open questions)."""

    def research(self, topic: str, niche: str = "") -> object:
        ...


@runtime_checkable
class ImageProvider(Protocol):
    """Fetches still images matching keywords. Returns local file paths."""

    def fetch_images(self, keywords: Sequence[str], count: int = 8) -> list[Path]:
        ...


@runtime_checkable
class VideoProvider(Protocol):
    """Fetches b-roll video clips matching keywords. Returns local file paths."""

    def fetch_videos(self, keywords: Sequence[str], count: int = 10) -> list[Path]:
        ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Synthesises narration audio for a script/text to a local file.

    Contract only for now — the concrete adapter over modules/audio_mixer.py is
    a follow-up (its constructor takes channel context and mixing config).
    """

    def synthesize(self, text: str, out_path: Path) -> Path:
        ...


@runtime_checkable
class PublishingProvider(Protocol):
    """Publishes a rendered video to a platform, returning at least an id/url.

    Contract only for now — the concrete adapter over
    modules/youtube_uploader.py is a follow-up.
    """

    def upload(self, video_path: Path, script: object, **kwargs) -> dict:
        ...


@runtime_checkable
class AnalyticsProvider(Protocol):
    """Reads back performance metrics for a published video.

    Contract only for now — the concrete adapter over
    modules/analytics_client.py is a follow-up.
    """

    def fetch_metrics(self, video_id: str) -> dict:
        ...


class GeminiResearchProvider:
    """Real ResearchProvider backed by the existing research_topic() function.

    A thin, honest adapter: it gives the module-level function a class shape so
    it satisfies the ResearchProvider protocol. It adds no behaviour of its own
    and imports research_topic lazily so importing this module stays cheap.
    """

    def research(self, topic: str, niche: str = "history mysteries") -> object:
        from modules.research_engine import research_topic

        return research_topic(topic, niche)


def research_provider() -> ResearchProvider:
    """The default research provider. A factory so a future config can swap the
    implementation without call sites changing."""
    return GeminiResearchProvider()
