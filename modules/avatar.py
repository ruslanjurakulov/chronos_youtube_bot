"""AITuber presenter layer — an optional synthetic on-camera character.

Nightshift is faceless by default (stock b-roll + narration). This adds the
*option* of an AI avatar presenter — an "AITuber" — as a provider behind the
seam in modules/providers.py. It is off unless a channel/series turns it on,
and it is bound by one hard rule:

    Only SYNTHETIC characters. Never clone a real person's face, never
    impersonate a public figure, never build an avatar from a photo of a real
    individual. This is enforced in code (synthetic_only_guard), not left to
    prompt hygiene — the spec's safety section is a requirement, not advice.

Provider
--------
`HiggsfieldAvatarProvider` targets Higgsfield's public API, which uses the
documented async lifecycle: submit a generation request, then poll for the
result (API-key auth). This module does NOT hardcode Higgsfield's endpoint
path or credentials — the operator supplies HIGGSFIELD_API_KEY and the base/
endpoint via environment, so nothing here is a guessed or faked call. Until
those are set, generate() raises AvatarUnavailable with exactly what to set,
the same "no silent fallback" posture as audio_mixer.verify_voice: a broken
avatar must fail loudly, never quietly ship a wrong or empty presenter.

Nothing here is wired into the render pipeline yet; enabling the presenter in a
run is a later, gated change (behind AvatarConfig.enabled and the publish gate,
which still decides every upload).
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class AvatarUnavailable(RuntimeError):
    """Raised when an avatar was asked for but the provider cannot deliver one
    (not configured, timed out, or refused). Callers must treat this as "no
    presenter", never as a reason to ship a blank or wrong one."""


class UnsafeAvatarRequest(ValueError):
    """Raised when an avatar request names or references a real person / public
    figure. Synthetic characters only — this is a safety stop, not a warning."""


@runtime_checkable
class AvatarProvider(Protocol):
    """Generates a presenter clip for narration. Returns a local file path."""

    def generate(self, prompt: str, character_ref: Optional[str], out_path: Path) -> Path:
        ...


# Markers that a reference is a real, identifiable person rather than a
# synthetic character. Deliberately conservative: when in doubt, refuse.
_REAL_PERSON_MARKERS = (
    "real person", "real people", "photo of", "photograph of", "likeness of",
    "deepfake", "face swap", "faceswap", "clone", "cloned", "lookalike",
    "impersonate", "impersonation", "celebrity", "public figure", "politician",
    "president", "actor", "actress", "singer", "influencer named",
)
# A reference that is a URL to an image/photo is treated as a real-person risk:
# a synthetic character is described, not sourced from someone's picture.
_IMAGE_URL_RE = re.compile(r"https?://\S+\.(?:png|jpe?g|webp|gif|bmp)\b", re.I)


def synthetic_only_guard(character_ref: Optional[str], prompt: str = "") -> None:
    """Refuse any request that reads as a real/identifiable person or a photo
    reference. Raises UnsafeAvatarRequest; returns None when the request is a
    plainly synthetic character description."""
    haystack = f"{character_ref or ''} {prompt or ''}".lower()
    if _IMAGE_URL_RE.search(character_ref or "") or _IMAGE_URL_RE.search(prompt or ""):
        raise UnsafeAvatarRequest(
            "Avatar references an image URL. Synthetic characters must be "
            "described, never built from a photo of a real person."
        )
    for marker in _REAL_PERSON_MARKERS:
        if marker in haystack:
            raise UnsafeAvatarRequest(
                f"Avatar request looks like a real/identifiable person ({marker!r}). "
                "Only synthetic characters are allowed."
            )


@dataclass(frozen=True)
class AvatarConfig:
    """Per-channel/series presenter settings. Off by default; a run stays
    faceless unless this is explicitly enabled."""

    enabled: bool = False
    provider: str = "higgsfield"
    # A synthetic character DESCRIPTION (never a real person / photo URL).
    character_prompt: str = ""
    character_ref: str = ""

    @staticmethod
    def from_mapping(data: Optional[dict]) -> "AvatarConfig":
        d = data or {}
        return AvatarConfig(
            enabled=bool(d.get("enabled", False)),
            provider=str(d.get("provider") or "higgsfield"),
            character_prompt=str(d.get("character_prompt") or ""),
            character_ref=str(d.get("character_ref") or ""),
        )


@dataclass(frozen=True)
class _HiggsfieldEnv:
    api_key: str
    base_url: str
    endpoint: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.endpoint)


class HiggsfieldAvatarProvider:
    """Real AvatarProvider over Higgsfield's async submit→poll API.

    Endpoint and credentials come from the environment so nothing is guessed:
      * HIGGSFIELD_API_KEY       — server-side credential
      * HIGGSFIELD_API_BASE      — API base URL (e.g. https://.../v1)
      * HIGGSFIELD_AVATAR_ENDPOINT — the avatar/talking-head model path
    When any is missing, generate() raises AvatarUnavailable naming what to set.
    """

    def __init__(self, *, poll_interval: float = 5.0, max_polls: int = 60):
        self.poll_interval = poll_interval
        self.max_polls = max_polls

    def _env(self) -> _HiggsfieldEnv:
        return _HiggsfieldEnv(
            api_key=os.getenv("HIGGSFIELD_API_KEY", "").strip(),
            base_url=os.getenv("HIGGSFIELD_API_BASE", "").strip().rstrip("/"),
            endpoint=os.getenv("HIGGSFIELD_AVATAR_ENDPOINT", "").strip(),
        )

    def generate(self, prompt: str, character_ref: Optional[str], out_path: Path) -> Path:
        # 1) Safety first — a real-person request never even reaches the network.
        synthetic_only_guard(character_ref, prompt)

        env = self._env()
        if not env.configured:
            raise AvatarUnavailable(
                "Higgsfield avatar is not configured. Set HIGGSFIELD_API_KEY, "
                "HIGGSFIELD_API_BASE and HIGGSFIELD_AVATAR_ENDPOINT to enable it. "
                "No presenter is generated until then (a blank/wrong avatar is "
                "never shipped)."
            )

        import requests  # local import: this module is usable (config/guard) without it

        headers = {"Authorization": f"Bearer {env.api_key}"}
        submit_url = f"{env.base_url}/{env.endpoint.lstrip('/')}"
        body = {"prompt": prompt}
        if character_ref:
            body["character"] = character_ref

        resp = requests.post(submit_url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        submitted = resp.json() if resp.content else {}
        job_id = submitted.get("id") or submitted.get("job_id") or submitted.get("request_id")
        if not job_id:
            raise AvatarUnavailable(f"Higgsfield submit returned no job id: {submitted!r}")

        # Poll the documented async lifecycle. Field access is defensive across
        # the common shapes (status/state, url/output_url/video_url); verify
        # against the live API response before enabling in production.
        status_url = f"{submit_url.rstrip('/')}/{job_id}"
        for _ in range(self.max_polls):
            poll = requests.get(status_url, headers=headers, timeout=30)
            poll.raise_for_status()
            data = poll.json() if poll.content else {}
            state = str(data.get("status") or data.get("state") or "").lower()
            if state in ("completed", "succeeded", "success", "done"):
                url = data.get("url") or data.get("output_url") or data.get("video_url")
                if not url:
                    raise AvatarUnavailable(f"Higgsfield job {job_id} finished with no output url")
                return self._download(url, out_path)
            if state in ("failed", "error", "canceled", "cancelled"):
                raise AvatarUnavailable(f"Higgsfield job {job_id} failed: {data!r}")
            time.sleep(self.poll_interval)
        raise AvatarUnavailable(f"Higgsfield job {job_id} did not finish after {self.max_polls} polls")

    @staticmethod
    def _download(url: str, out_path: Path) -> Path:
        import requests

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        return out_path


def avatar_provider(config: AvatarConfig) -> Optional[AvatarProvider]:
    """The provider for a config, or None when avatars are off. A factory so a
    future provider can be selected by name without call sites changing."""
    if not config.enabled:
        return None
    if config.provider == "higgsfield":
        return HiggsfieldAvatarProvider()
    raise AvatarUnavailable(f"Unknown avatar provider {config.provider!r}")
