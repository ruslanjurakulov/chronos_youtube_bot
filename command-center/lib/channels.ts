/**
 * Channel selection and channel-scoped derivations.
 *
 * Two things live here:
 *
 * 1. **Which channel is selected** — a cookie the switcher writes and the
 *    server reads, so a Server Component can scope its queries before it
 *    renders rather than fetching everything and hiding rows in the browser.
 * 2. **Pure derivations** over already-fetched rows (health, per-channel
 *    aggregates), unit-tested like every other derivation in lib/.
 *
 * A note on what filtering is and is not: it is a *view* control, not a
 * security boundary. RLS decides what a logged-in user may read at all; the
 * selection here decides what they are looking at right now. Neither substitutes
 * for the other.
 */

import type {
  ChannelCredentialRow,
  ChannelRow,
  MetricsSnapshotRow,
  SystemEventRow,
  VideoRow,
} from "@/lib/types";
import { storedMs } from "@/lib/format";

/** Remembers the last channel viewed, so "/" knows where to send you. It is a
 *  memory, not the selection — the URL is the selection. */
export const CHANNEL_COOKIE = "chronos_channel";

/** Request header the middleware fills from the URL's channel segment. */
export const CHANNEL_HEADER = "x-nightshift-channel";

/** Request header carrying the full pathname, which a layout cannot otherwise see. */
export const PATH_HEADER = "x-nightshift-path";

/** The sentinel for "don't filter". Not a channel id — no channel may be named this. */
export const ALL_CHANNELS = "__all__";

/** How ALL_CHANNELS is spelled in a URL. Reserved: no channel may take it. */
export const ALL_CHANNELS_SLUG = "all-channels";

/**
 * Every section path, without a channel prefix.
 *
 * The middleware needs this to tell an old-style link (`/videos`) from a
 * channel segment (`/chronos`), since both are one path segment. Keep it in
 * step with the routes under `app/(app)/[channel]/`.
 */
export const SECTIONS = [
  "command-center",
  "videos",
  "pipeline",
  "analytics",
  "channels",
  "intelligence-map",
  "agents",
  "jobs",
  "topics",
  "measurement",
  "decisions",
  "learning",
  "memory",
  "autonomy",
  "feedback-loop",
  "time-machine",
  "errors",
  "logs",
  "integrations",
] as const;

/** True when `segment` names a section rather than a channel. */
export function isSection(segment: string): boolean {
  return (SECTIONS as readonly string[]).includes(segment);
}

/** URL segment → selection. */
export function slugToSelection(slug: string): ChannelSelection {
  return slug === ALL_CHANNELS_SLUG ? ALL_CHANNELS : slug;
}

/** Selection → URL segment. */
export function selectionToSlug(selection: ChannelSelection): string {
  return selection === ALL_CHANNELS ? ALL_CHANNELS_SLUG : selection;
}

/** `/chronos/videos` from ("chronos", "/videos"). */
export function channelPath(slug: string, section: string): string {
  return `/${slug}${section}`;
}

export const DEFAULT_CHANNEL_ID = "default";

export type ChannelSelection = string; // a channel_id, or ALL_CHANNELS

/**
 * Resolve a raw cookie value against the channels that actually exist.
 *
 * A selection naming a channel that has since been deleted (or that this user
 * cannot see) falls back to ALL_CHANNELS rather than showing an empty app with
 * no explanation.
 */
export function resolveSelection(
  raw: string | undefined,
  channels: ChannelRow[],
): ChannelSelection {
  if (!raw || raw === ALL_CHANNELS || raw === ALL_CHANNELS_SLUG) return ALL_CHANNELS;
  if (channels.some((c) => c.channel_id === raw)) return raw;
  // Also accept the channel's readable slug, so /chronos/… resolves even though
  // the row's id is "default". The id keeps working: it is what every old link
  // and every foreign key says.
  const byName = channels.find((c) => channelSlug(c, channels) === raw);
  return byName ? byName.channel_id : ALL_CHANNELS;
}

/**
 * The URL segment for a channel — its name, not its internal key.
 *
 * `channel_id` is a database key: it is what `videos.channel_id` and every
 * other row points at, and renaming it would mean rewriting all of them. But it
 * is also the first thing the operator reads in the address bar, and the
 * production channel's id is "default", which tells them nothing. So the URL
 * shows the channel's NAME — /chronos/pipeline — while the id stays where it
 * belongs, in the database.
 *
 * The id is used instead whenever the name cannot stand in for it without
 * ambiguity: when it slugifies to nothing usable, to a reserved word, to
 * something two channels share, or to another channel's id. In every one of
 * those cases the id is the only unambiguous answer, so it wins — a URL is
 * allowed to be ugly, never ambiguous.
 */
export function channelSlug(channel: ChannelRow, channels: ChannelRow[]): string {
  const candidate = slugifyChannelId(channel.name ?? "");
  if (!candidate || !isValidChannelId(candidate)) return channel.channel_id;
  const claimedByAnother = channels.some(
    (c) =>
      c.channel_id !== channel.channel_id &&
      (c.channel_id === candidate || slugifyChannelId(c.name ?? "") === candidate),
  );
  return claimedByAnother ? channel.channel_id : candidate;
}

/** The URL segment for a selection: a channel's name-slug, or "all-channels". */
export function selectionSlug(
  selection: ChannelSelection,
  channels: ChannelRow[],
): string {
  if (!isScoped(selection)) return ALL_CHANNELS_SLUG;
  const channel = channels.find((c) => c.channel_id === selection);
  return channel ? channelSlug(channel, channels) : selection;
}

/** True when the view is scoped to exactly one channel. */
export function isScoped(selection: ChannelSelection): boolean {
  return selection !== ALL_CHANNELS;
}

/**
 * Apply the selection to a Supabase query builder.
 *
 * `nullIsGlobal` is for system_events, where a null channel_id means the event
 * belongs to no channel (a heartbeat, an infrastructure failure). Those stay
 * visible while scoped to one channel — an operator watching Finance still
 * needs to know the database is down — so the filter is "mine OR global".
 */
export function scopeQuery<Q extends object>(
  query: Q,
  selection: ChannelSelection,
  { nullIsGlobal = false, column = "channel_id" }: { nullIsGlobal?: boolean; column?: string } = {},
): Q {
  if (!isScoped(selection)) return query;
  // Structurally typed rather than constrained to the Supabase builder: naming
  // that type in the constraint makes TypeScript walk its (very deep) generic
  // parameters at every call site and bail with TS2589.
  const filterable = query as unknown as {
    eq: (column: string, value: string) => Q;
    or: (filter: string) => Q;
  };
  return nullIsGlobal
    ? filterable.or(`${column}.eq.${selection},${column}.is.null`)
    : filterable.eq(column, selection);
}

/** Does this row belong to the current view? Mirrors scopeQuery, for arrays. */
export function inSelection(
  rowChannelId: string | null | undefined,
  selection: ChannelSelection,
  { nullIsGlobal = false }: { nullIsGlobal?: boolean } = {},
): boolean {
  if (!isScoped(selection)) return true;
  if (rowChannelId == null) return nullIsGlobal;
  return rowChannelId === selection;
}

export function channelName(channels: ChannelRow[], id: string | null | undefined): string {
  if (!id) return "";
  return channels.find((c) => c.channel_id === id)?.name ?? id;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export type HealthTone = "ok" | "warn" | "fail" | "idle";

export interface SubsystemHealth {
  key: "youtube" | "scheduler" | "generator" | "analytics";
  tone: HealthTone;
  /** A short, factual reason. Empty when the state speaks for itself. */
  detail: string;
}

export interface ChannelHealth {
  channelId: string;
  tone: HealthTone;
  /** True when a human has to do something (a token expired, say). */
  actionRequired: boolean;
  subsystems: SubsystemHealth[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Health for one channel, derived only from what the backend actually recorded.
 *
 * Deliberately per channel: one channel's expired token is that channel's
 * problem, and must not make the whole of Chronos read as unhealthy. Where
 * there is no evidence either way the tone is "idle", never a green tick —
 * "we have not heard from this subsystem" is not the same as "it is fine".
 */
export function channelHealth(
  channel: ChannelRow,
  events: SystemEventRow[],
  credential: ChannelCredentialRow | undefined,
  now: number = Date.now(),
): ChannelHealth {
  const mine = events.filter((e) => e.channel_id === channel.channel_id);
  const recent = mine.filter((e) => now - (storedMs(e.ts) ?? 0) < 2 * DAY_MS);

  // -- YouTube: exactly what the credential mirror reported.
  let youtube: SubsystemHealth = { key: "youtube", tone: "idle", detail: "" };
  if (credential) {
    const tone: HealthTone =
      credential.status === "connected"
        ? "ok"
        : credential.status === "expired" || credential.status === "error"
          ? "fail"
          : "idle";
    youtube = { key: "youtube", tone, detail: credential.detail ?? "" };
  }

  // -- Scheduler: a channel that is PAUSED or schedule-disabled is idle by
  // choice, which is not a fault. An ACTIVE channel that has produced no event
  // in two days is worth flagging.
  const scheduleEnabled = channel.schedule_config?.enabled !== false;
  const active = channel.status === "ACTIVE" && scheduleEnabled;
  const scheduler: SubsystemHealth = !active
    ? { key: "scheduler", tone: "idle", detail: "" }
    : recent.length > 0
      ? { key: "scheduler", tone: "ok", detail: "" }
      : { key: "scheduler", tone: "warn", detail: "no activity in 48h" };

  // -- Generator / analytics: failures the backend recorded, by agent.
  const generator = agentHealth("generator", recent, [
    "script_engine",
    "audio_mixer",
    "compositor",
    "media_fetcher",
  ]);
  const analytics = agentHealth("analytics", recent, ["intelligence_poller", "feedback_engine"]);

  const subsystems = [youtube, scheduler, generator, analytics];
  const tone: HealthTone = subsystems.some((s) => s.tone === "fail")
    ? "fail"
    : subsystems.some((s) => s.tone === "warn")
      ? "warn"
      : subsystems.some((s) => s.tone === "ok")
        ? "ok"
        : "idle";

  return {
    channelId: channel.channel_id,
    tone,
    actionRequired: youtube.tone === "fail",
    subsystems,
  };
}

/** Health of one named subsystem, from the failures its agents actually
 *  recorded. Takes the key rather than hardcoding one the caller then has to
 *  overwrite. No events at all is "idle", never a green tick. */
function agentHealth(
  key: SubsystemHealth["key"],
  events: SystemEventRow[],
  agents: string[],
): SubsystemHealth {
  const mine = events.filter((e) => e.agent && agents.includes(e.agent));
  if (mine.length === 0) return { key, tone: "idle", detail: "" };
  const failed = mine.filter((e) => e.status === "failed");
  if (failed.length === 0) return { key, tone: "ok", detail: "" };
  return {
    key,
    tone: "fail",
    detail: `${failed.length} failure${failed.length === 1 ? "" : "s"} in 48h`,
  };
}

// ---------------------------------------------------------------------------
// Cross-channel comparison
// ---------------------------------------------------------------------------

export interface ChannelStats {
  channelId: string;
  name: string;
  status: string;
  videos: number;
  views: number | null;
  /** Mean views per video, or null when no video has a metrics snapshot yet. */
  avgViews: number | null;
  /** Days between the first and last publish, divided by videos. Null under 2. */
  daysPerVideo: number | null;
  lastPublishedAt: string | null;
}

/**
 * Per-channel totals for the comparison view.
 *
 * `views` is null rather than 0 when no video of that channel has a metrics
 * snapshot: a channel with unpolled videos has *unknown* views, and rendering
 * that as zero would make a working channel look dead. Only comparable things
 * are computed here — there is deliberately no blended "score" mixing views
 * with cadence, because that number would mean nothing.
 */
export function channelStats(
  channels: ChannelRow[],
  videos: VideoRow[],
  snapshots: MetricsSnapshotRow[],
): ChannelStats[] {
  const latestByVideo = new Map<string, MetricsSnapshotRow>();
  for (const s of snapshots) {
    const seen = latestByVideo.get(s.video_id);
    if (!seen || s.snapshot_date > seen.snapshot_date) latestByVideo.set(s.video_id, s);
  }

  return channels.map((c) => {
    const mine = videos.filter((v) => v.channel_id === c.channel_id);
    const measured = mine
      .map((v) => latestByVideo.get(v.video_id))
      .filter((s): s is MetricsSnapshotRow => Boolean(s));
    const views = measured.length ? measured.reduce((sum, s) => sum + (s.views ?? 0), 0) : null;

    const dates = mine
      .map((v) => v.published_at)
      .filter((d): d is string => Boolean(d))
      .sort();
    const span =
      dates.length >= 2
        ? (new Date(dates[dates.length - 1]).getTime() - (storedMs(dates[0]) ?? 0)) / DAY_MS
        : null;

    return {
      channelId: c.channel_id,
      name: c.name,
      status: c.status,
      videos: mine.length,
      views,
      avgViews: views !== null && measured.length ? Math.round(views / measured.length) : null,
      daysPerVideo: span !== null && span > 0 ? Number((span / (mine.length - 1)).toFixed(1)) : null,
      lastPublishedAt: dates.length ? dates[dates.length - 1] : null,
    };
  });
}

/** A channel id the user typed, validated against the same rule the bot uses. */
export function isValidChannelId(value: string): boolean {
  // A channel id is also a URL segment, so it may not collide with the words
  // that segment already means — otherwise /videos would be ambiguous between
  // "the Videos section" and "a channel called videos".
  if (value === ALL_CHANNELS_SLUG || isSection(value)) return false;
  return /^[a-z0-9][a-z0-9-]{1,38}$/.test(value);
}

/** Turn a display name into a candidate channel id. */
export function slugifyChannelId(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 39);
}

/**
 * The one channel exempt from confirmation.
 *
 * It predates the registry: it is the single channel this bot has always
 * published as, its identity comes from the bot's `config.py`, and it never
 * passed through a form that could have confirmed it.
 */
export const LEGACY_CHANNEL_ID = "default";

/**
 * Has a real YouTube channel ever answered for this row?
 *
 * Both halves are required. A `verified_at` stamp alone could be written by
 * hand; a channel id alone could be a typo that never resolved. Together they
 * say a lookup happened and returned something.
 *
 * Without this, a channel created from a typed name, a typed niche and a
 * guessed id was indistinguishable from a real one — and the scheduler ran it.
 * The same rule is enforced in the database (migration 0005) and in the bot's
 * registry, so no single layer carries it alone.
 */
export function isChannelVerified(
  channel: Pick<ChannelRow, "channel_id" | "credential_ref">,
): boolean {
  if (channel.channel_id === LEGACY_CHANNEL_ID) return true;
  const ref = channel.credential_ref;
  return Boolean(ref?.verified_at && ref?.youtube_channel_id);
}

/**
 * Which ElevenLabs voice belongs to which channel, voice id -> display name.
 *
 * Two channels narrated by the same voice sound like one channel with two
 * names, which is the opposite of why there is more than one. The creation
 * wizard greys out the voices this returns, so a collision is impossible to
 * select rather than rejected on save.
 */
export function voiceOwners(channels: ChannelRow[]): Record<string, string> {
  const owners: Record<string, string> = {};
  for (const c of channels) {
    const agent = c.agent_config ?? {};
    if (agent.tts_provider !== "elevenlabs") continue;
    const voice = (agent.elevenlabs_voice_id ?? "").trim();
    if (voice && !owners[voice]) owners[voice] = c.name || c.channel_id;
  }
  return owners;
}
