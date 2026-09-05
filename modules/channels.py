"""Channel model — the configuration one Chronos channel runs under.

Chronos began as a single-channel bot: every generator read its settings from
module-level constants in ``config.py``, which read the process environment
once at import time. That works for exactly one channel. This module adds the
missing noun — a *channel* — without taking those constants away.

The shape
---------
``ChannelContext`` is an immutable bundle of everything a pipeline run needs to
know about *which* channel it is working for: identity (``channel_id``,
``name``, ``niche``), the generator settings (``AgentConfig``), when it runs
(``ScheduleConfig``), and *which* credential to publish with
(``CredentialRef`` — a reference, never a secret; see
``modules/channel_credentials.py``). It is passed down the pipeline as an
argument rather than read from a global, so a worker handling channel A cannot
accidentally pick up channel B's voice, style, or token.

Backward compatibility — the important part
---------------------------------------------
``ChannelRegistry.load()`` resolves configuration from, in order:

1. **Supabase** (``channels`` table) when ``SUPABASE_URL`` /
   ``SUPABASE_SERVICE_KEY`` are set — this is what the Command Center's
   channel management writes to.
2. **``channels.json``** in the repo root (or ``CHRONOS_CHANNELS_FILE``) — a
   checked-in / cached file, useful without Supabase.
3. **The legacy default channel**, built from today's ``config.py`` values.

Step 3 is the guarantee: with nothing configured anywhere, the registry hands
back exactly one channel, id ``"default"``, whose voice / language / duration /
YouTube target are the same constants the single-channel bot already used. So
an unconfigured deployment behaves precisely as it does today.

Any failure to load a remote or file source is logged and falls through to the
next source; the registry never raises into the pipeline. A malformed
``channels.json`` must not be able to stop the production channel from
publishing.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NewType, Optional

import config as cfg

logger = logging.getLogger(__name__)

# A channel id is a slug, not a free-form string: it names token files, env
# vars and DB rows, so it stays in a conservative character set.
ChannelId = NewType("ChannelId", str)

DEFAULT_CHANNEL_ID: ChannelId = ChannelId("default")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}$")

# Statuses. Deliberately only two, per the brief — a channel either runs on its
# schedule or it does not.
STATUS_ACTIVE = "ACTIVE"
STATUS_PAUSED = "PAUSED"
_STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)


def validate_channel_id(value: str) -> ChannelId:
    """Return `value` as a ChannelId, or raise ValueError if it isn't a slug."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(
            f"Invalid channel id {value!r} — expected a lowercase slug like "
            "'extinct-world' (2-39 chars, a-z 0-9 and dashes, not leading with a dash)"
        )
    return ChannelId(value)


def normalize_status(value: str | None) -> str:
    """Coerce a status string to ACTIVE/PAUSED. Unknown values read as PAUSED —
    the safe direction: an unrecognised status must never cause a channel to
    start publishing on its own."""
    upper = (value or "").strip().upper()
    return upper if upper in _STATUSES else STATUS_PAUSED


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_competitor_ids() -> list[str]:
    """The process-wide COMPETITOR_CHANNEL_IDS, as the default channel's list.

    Pre-Phase-5 deployments configured competitors through this one env var, so
    it remains the fallback. A channel that names its own competitors overrides
    it entirely — a Finance channel must not inherit a history channel's rivals.
    """
    raw = os.getenv("COMPETITOR_CHANNEL_IDS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _clean_ids(value) -> tuple:
    """Parse competitor ids from a stored list or a comma-separated string.

    An absent key falls back to the env var (the legacy behaviour); an explicit
    empty list means "watch nobody", which is different and is honoured.
    """
    if value is None:
        return tuple(_env_competitor_ids())
    if isinstance(value, str):
        return tuple(c.strip() for c in value.split(",") if c.strip())
    try:
        return tuple(str(c).strip() for c in value if str(c).strip())
    except TypeError:
        return ()


@dataclass(frozen=True)
class AgentConfig:
    """Per-channel generator settings.

    Every field defaults to the corresponding ``config.py`` constant, so a
    channel that specifies nothing generates exactly what the single-channel
    bot generates. Values are resolved at *construction* time from config so
    the defaults follow the environment the process actually runs in.
    """

    language: str = field(default_factory=lambda: cfg.SCRIPT_LANGUAGE)
    target_duration_seconds: int = field(default_factory=lambda: cfg.VIDEO_DURATION_TARGET)
    tts_provider: str = field(default_factory=lambda: cfg.TTS_PROVIDER)
    elevenlabs_voice_id: str = field(default_factory=lambda: cfg.ELEVENLABS_VOICE_ID)
    edge_tts_voice: str = field(default_factory=lambda: cfg.EDGE_TTS_VOICE)
    # Free-text prompt fragments. Appended to the shared prompts rather than
    # replacing them — the retention rules in script_engine.SCRIPT_SYSTEM_PROMPT
    # apply to every channel; a channel adds its strategy on top.
    system_prompt: str = ""
    niche_rules: str = ""
    visual_style_prompt: str = ""
    # Which YouTube channels THIS channel watches. Strictly speaking a
    # monitoring setting rather than a generator one, but it lives in the same
    # JSON blob so a channel's whole configuration stays in one column and adding
    # it costs no second migration. A tuple because AgentConfig is frozen.
    competitor_channel_ids: tuple = field(
        default_factory=lambda: tuple(_env_competitor_ids())
    )
    # Which pre-publish checks are live for this channel. Empty means every
    # check is on — see modules/publish_gate.GateConfig, where only an explicit
    # `false` turns one off, so a config typo cannot silently disable a safety
    # check.
    publish_gate: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "target_duration_seconds": self.target_duration_seconds,
            "tts_provider": self.tts_provider,
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
            "edge_tts_voice": self.edge_tts_voice,
            "system_prompt": self.system_prompt,
            "niche_rules": self.niche_rules,
            "visual_style_prompt": self.visual_style_prompt,
            "competitor_channel_ids": list(self.competitor_channel_ids),
            "publish_gate": dict(self.publish_gate),
        }

    @staticmethod
    def from_dict(d: dict | None) -> "AgentConfig":
        d = d or {}
        base = AgentConfig()
        duration = d.get("target_duration_seconds", base.target_duration_seconds)
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = base.target_duration_seconds
        return replace(
            base,
            language=d.get("language") or base.language,
            target_duration_seconds=duration,
            tts_provider=d.get("tts_provider") or base.tts_provider,
            elevenlabs_voice_id=d.get("elevenlabs_voice_id") or base.elevenlabs_voice_id,
            edge_tts_voice=d.get("edge_tts_voice") or base.edge_tts_voice,
            system_prompt=d.get("system_prompt") or "",
            niche_rules=d.get("niche_rules") or "",
            visual_style_prompt=d.get("visual_style_prompt") or "",
            competitor_channel_ids=_clean_ids(d.get("competitor_channel_ids")),
            publish_gate=dict(d.get("publish_gate") or {}),
        )


@dataclass(frozen=True)
class ScheduleConfig:
    """When this channel's daily run fires.

    `publish_hour_utc` is the hour the scheduler *intends* to run at. The
    actual trigger is still GitHub Actions cron (see .github/workflows), which
    cannot be written per-row from a database; the scheduler workflow decides
    which channels a given firing covers by comparing this value. `enabled`
    off means "never scheduled", independent of channel status.
    """

    publish_hour_utc: Optional[int] = None
    enabled: bool = True

    def to_dict(self) -> dict:
        return {"publish_hour_utc": self.publish_hour_utc, "enabled": self.enabled}

    @staticmethod
    def from_dict(d: dict | None) -> "ScheduleConfig":
        d = d or {}
        hour = d.get("publish_hour_utc")
        try:
            hour = int(hour) if hour is not None else None
        except (TypeError, ValueError):
            hour = None
        if hour is not None and not (0 <= hour <= 23):
            hour = None
        return ScheduleConfig(publish_hour_utc=hour, enabled=bool(d.get("enabled", True)))


@dataclass(frozen=True)
class CredentialRef:
    """*Reference* to a channel's publishing credential — never the credential.

    `ref` names where the secret lives (an env var / GitHub secret suffix), and
    `youtube_channel_id` is the public channel id the upload targets. Resolving
    a ref to an actual token happens server-side only, in
    ``modules/channel_credentials.py``. Nothing in this dataclass is a secret,
    which is why it is safe to mirror to Supabase and render in the Command
    Center.
    """

    provider: str = "youtube"
    ref: str = ""
    youtube_channel_id: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "ref": self.ref,
            "youtube_channel_id": self.youtube_channel_id,
        }

    @staticmethod
    def from_dict(d: dict | None) -> "CredentialRef":
        d = d or {}
        return CredentialRef(
            provider=d.get("provider") or "youtube",
            ref=d.get("ref") or "",
            youtube_channel_id=d.get("youtube_channel_id") or "",
        )


@dataclass(frozen=True)
class ChannelContext:
    """One channel, fully resolved. Flows through the pipeline as an argument.

    Frozen on purpose: a pipeline stage must not be able to mutate the context
    a later stage will read, and two channels running in the same process (or
    in the same test) must not be able to reach each other's settings.
    """

    channel_id: ChannelId
    name: str
    niche: str
    status: str = STATUS_ACTIVE
    agent: AgentConfig = field(default_factory=AgentConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    credential: CredentialRef = field(default_factory=CredentialRef)
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    @property
    def is_default(self) -> bool:
        return self.channel_id == DEFAULT_CHANNEL_ID

    def to_dict(self) -> dict:
        return {
            "channel_id": str(self.channel_id),
            "name": self.name,
            "niche": self.niche,
            "status": self.status,
            "agent_config": self.agent.to_dict(),
            "schedule_config": self.schedule.to_dict(),
            "credential_ref": self.credential.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "ChannelContext":
        """Build a context from a stored row/JSON object. Raises ValueError for
        a missing or malformed channel id — the one field with no sane
        fallback."""
        channel_id = validate_channel_id(str(d.get("channel_id") or ""))
        return ChannelContext(
            channel_id=channel_id,
            name=d.get("name") or str(channel_id),
            niche=d.get("niche") or "",
            status=normalize_status(d.get("status")),
            agent=AgentConfig.from_dict(d.get("agent_config")),
            schedule=ScheduleConfig.from_dict(d.get("schedule_config")),
            credential=CredentialRef.from_dict(d.get("credential_ref")),
            created_at=d.get("created_at") or "",
            updated_at=d.get("updated_at") or "",
        )


def legacy_default_channel() -> ChannelContext:
    """The single channel this bot has always run as, expressed as a context.

    Everything comes from ``config.py``, so with no channels configured the
    pipeline resolves this and behaves exactly as the single-channel bot did.
    Its status is ACTIVE — the production channel must not silently stop
    publishing because a multi-channel registry was introduced.
    """
    return ChannelContext(
        channel_id=DEFAULT_CHANNEL_ID,
        name=os.getenv("CHRONOS_DEFAULT_CHANNEL_NAME", "Chronos"),
        niche=os.getenv("CHRONOS_DEFAULT_CHANNEL_NICHE", "history mysteries"),
        status=STATUS_ACTIVE,
        agent=AgentConfig(),
        schedule=ScheduleConfig(publish_hour_utc=15, enabled=True),
        credential=CredentialRef(
            provider="youtube",
            ref="",  # empty ref = the legacy token file / YOUTUBE_TOKEN_JSON secret
            youtube_channel_id=cfg.YOUTUBE_CHANNEL_ID,
        ),
    )


class ChannelRegistry:
    """Loads channel configuration and hands out ``ChannelContext`` objects.

    Also known, in the brief's terms, as the *Channel Agent Manager*: the one
    place that knows how to turn a channel id into the configuration every
    agent (script, voice, visuals, publishing, analytics, learning) should run
    under. There is one reusable pipeline; this supplies its context.

    Loading is lazy and cached per instance. Construct a fresh registry (or
    call ``reload()``) to pick up changes.
    """

    def __init__(
        self,
        channels: Optional[Iterable[ChannelContext]] = None,
        *,
        file_path: Optional[Path | str] = None,
        sync=None,
    ):
        # An explicit `channels` list short-circuits every source — this is how
        # tests inject a fixed set without touching Supabase or the filesystem.
        self._explicit = list(channels) if channels is not None else None
        self._file_path = Path(file_path) if file_path is not None else _default_file_path()
        self._sync = sync
        self._cache: Optional[dict[ChannelId, ChannelContext]] = None

    # -- loading -----------------------------------------------------------

    def reload(self) -> "ChannelRegistry":
        self._cache = None
        return self

    def _load(self) -> dict[ChannelId, ChannelContext]:
        if self._cache is not None:
            return self._cache

        contexts: list[ChannelContext] = []
        if self._explicit is not None:
            contexts = list(self._explicit)
        else:
            contexts = self._load_from_supabase()
            if not contexts:
                contexts = self._load_from_file()

        by_id: dict[ChannelId, ChannelContext] = {}
        for ctx in contexts:
            by_id[ctx.channel_id] = ctx

        # The default channel always exists. If a source defined it, that
        # definition wins; otherwise the legacy one is synthesized so callers
        # can always resolve DEFAULT_CHANNEL_ID.
        if DEFAULT_CHANNEL_ID not in by_id:
            by_id[DEFAULT_CHANNEL_ID] = legacy_default_channel()

        self._cache = by_id
        return by_id

    def _load_from_supabase(self) -> list[ChannelContext]:
        """Read the `channels` table. Returns [] when Supabase isn't configured
        or the read fails — never raises."""
        try:
            sync = self._sync
            if sync is None:
                from modules.supabase_sync import SupabaseSync

                sync = SupabaseSync()
            if not getattr(sync, "enabled", False):
                return []
            rows = sync.select("channels")
        except Exception as e:
            logger.warning(
                "Failed loading channels from Supabase (%s: %s) — falling back to local config",
                type(e).__name__, e,
            )
            return []
        return _parse_rows(rows, source="supabase")

    def _load_from_file(self) -> list[ChannelContext]:
        path = self._file_path
        try:
            if not path or not path.exists():
                return []
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            data = json.loads(raw)
        except Exception as e:
            logger.warning(
                "Failed reading channels file %s (%s: %s) — falling back to the default channel",
                path, type(e).__name__, e,
            )
            return []
        rows = data.get("channels") if isinstance(data, dict) else data
        return _parse_rows(rows if isinstance(rows, list) else [], source=str(path))

    # -- public API --------------------------------------------------------

    def get(self, channel_id: str | None = None) -> ChannelContext:
        """Resolve one channel. `None` means the default channel.

        Raises KeyError for an unknown id — a typo'd channel must fail loudly
        rather than silently publishing to whichever channel happens to be
        first.
        """
        wanted = DEFAULT_CHANNEL_ID if channel_id is None else validate_channel_id(str(channel_id))
        channels = self._load()
        if wanted not in channels:
            known = ", ".join(sorted(str(c) for c in channels))
            raise KeyError(f"Unknown channel {wanted!r}. Known channels: {known}")
        return channels[wanted]

    def list(self, status: str | None = None) -> list[ChannelContext]:
        """All channels, optionally filtered by status, default channel first
        then alphabetical — a stable order for logs and matrices."""
        channels = list(self._load().values())
        if status is not None:
            wanted = normalize_status(status)
            channels = [c for c in channels if c.status == wanted]
        channels.sort(key=lambda c: (not c.is_default, str(c.channel_id)))
        return channels

    def active(self) -> list[ChannelContext]:
        """Channels the scheduler may run: ACTIVE *and* schedule-enabled."""
        return [c for c in self.list(status=STATUS_ACTIVE) if c.schedule.enabled]

    def ids(self) -> list[ChannelId]:
        return [c.channel_id for c in self.list()]


def _parse_rows(rows, *, source: str) -> list[ChannelContext]:
    """Parse stored rows into contexts, skipping (and logging) bad ones.

    One malformed row must not hide every other channel — a broken Finance row
    should not stop History from running.
    """
    out: list[ChannelContext] = []
    for row in rows or []:
        try:
            out.append(ChannelContext.from_dict(dict(row)))
        except Exception as e:
            logger.warning(
                "Skipping malformed channel row from %s (%s: %s)", source, type(e).__name__, e
            )
    return out


def _default_file_path() -> Path:
    override = os.getenv("CHRONOS_CHANNELS_FILE")
    return Path(override) if override else (cfg.BASE_DIR / "channels.json")


# A module-level registry for callers that just want "the channels", plus an
# explicit reset for tests.
_registry: Optional[ChannelRegistry] = None


def get_registry() -> ChannelRegistry:
    global _registry
    if _registry is None:
        _registry = ChannelRegistry()
    return _registry


def reset_registry() -> None:
    """Drop the cached module-level registry (tests, and after a config write)."""
    global _registry
    _registry = None


def resolve_channel(channel_id: str | None = None) -> ChannelContext:
    """Convenience: resolve one channel through the shared registry."""
    return get_registry().get(channel_id)


def new_channel(
    channel_id: str,
    name: str,
    niche: str,
    *,
    agent: AgentConfig | None = None,
    schedule: ScheduleConfig | None = None,
    credential: CredentialRef | None = None,
) -> ChannelContext:
    """Build a brand-new channel context.

    Deliberately PAUSED: per the brief, creating a channel must never start
    publishing. A human activates it explicitly.
    """
    now = _now_iso()
    return ChannelContext(
        channel_id=validate_channel_id(channel_id),
        name=name,
        niche=niche,
        status=STATUS_PAUSED,
        agent=agent or AgentConfig(),
        schedule=schedule or ScheduleConfig(),
        credential=credential or CredentialRef(),
        created_at=now,
        updated_at=now,
    )
