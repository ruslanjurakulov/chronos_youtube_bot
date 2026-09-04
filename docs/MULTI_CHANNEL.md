# Multi-channel architecture (Phase 5)

Chronos runs several independent YouTube channels from one Command Center. This
document describes what a channel *is*, what is scoped to it and what stays
global, how credentials are kept out of the browser, and exactly what a
single-channel deployment does and does not have to change.

**Short version for an existing deployment: nothing.** With no channel
configured anywhere, the registry resolves one channel — `default` — built from
the same `.env` values the bot has always read, and every stage behaves exactly
as it did before. The migration is additive and backfills existing rows to that
channel. Multi-channel is opt-in.

---

## 1. What a channel is

`modules/channels.py`

| Field | Meaning |
| --- | --- |
| `channel_id` | A validated slug (`^[a-z0-9][a-z0-9-]{1,38}$`). Permanent — it keys every row. |
| `name`, `niche` | Identity. `niche` is the default topic area for its runs. |
| `status` | `ACTIVE` or `PAUSED`. Anything unrecognised reads as `PAUSED`. |
| `agent` (`AgentConfig`) | Language, target duration, TTS provider, narrator voice, content strategy, niche rules, visual style. |
| `schedule` (`ScheduleConfig`) | `publish_hour_utc`, `enabled`. |
| `credential` (`CredentialRef`) | Provider, the *reference* to a secret, and the public YouTube channel id. **Never a token.** |

`ChannelContext` bundles these and is **frozen**. It is passed down the pipeline
as an argument, never read from a global, so a worker handling channel A cannot
pick up channel B's settings.

### Where configuration comes from

`ChannelRegistry.load()` resolves, in order:

1. **Supabase** `channels` table — what the Command Center's Channels page writes.
2. **`channels.json`** at the repo root (or `CHRONOS_CHANNELS_FILE`). See
   `channels.example.json`.
3. **The legacy default channel**, built from `config.py`.

Step 3 is the backward-compatibility guarantee. A failure at any level is logged
and falls through to the next; a malformed row is skipped rather than raised, so
one broken Finance row cannot stop History from running.

---

## 2. Global vs channel data

**Channel-scoped** — added by `supabase/migrations/0001_multi_channel.sql`:

| Table | Column |
| --- | --- |
| `videos`, `feedback_signals`, `demand_signals`, `content_queue`, `pipeline_runs` | `channel_id` (NOT NULL DEFAULT `'default'`) |
| `competitor_snapshots` | `chronos_channel_id` — **not** `channel_id`, which already exists and means the *competitor's* YouTube channel |
| `system_events` | `channel_id`, **nullable** |
| `channel_topic_performance` | new table, PK `(channel_id, topic)` |

**Global on purpose:**

- `trending_snapshots` — region-wide YouTube data, not any channel's.
- `metrics_snapshots` — reached through its video's `channel_id`; duplicating it
  would give two places to disagree.
- `system_events` with a **null** `channel_id`. Null here means *global*, not
  *unknown*: a system heartbeat or an infrastructure failure is not any one
  channel's doing, and a default would attribute it to whichever channel ran
  last. Scoped views show "mine OR global", because an operator watching Finance
  still needs to know the database is down.

### Why `topic_performance` was left alone

Its primary key is `topic` alone, so it structurally cannot hold two channels'
verdicts on the same topic string. Changing a primary key means dropping one,
which is a destructive migration. Instead:

- `channel_topic_performance` (PK `(channel_id, topic)`) holds the isolated
  per-channel score, and every channel writes there.
- `topic_performance` is still written **for the default channel only**, so it
  stays correct for a single-channel deployment and for historical data. A
  non-default channel never writes it — that write would overwrite another
  channel's verdict, which is exactly the contamination this phase prevents.
- The Command Center reads the channel table when scoped and the shared table in
  the all-channels view, and says so on the Topics page. Per-channel verdicts
  are never averaged together: that number would describe neither channel.

---

## 3. Credentials

**The rule: a refresh token never reaches the browser, a database column, a log
line or an event.**

- The secret lives where this project's secrets already live — a GitHub Actions
  secret, materialized into a token file for the life of one job. That is
  exactly what the workflow already did for the single channel.
- `channel_credentials` in Supabase stores **status only**: connected /
  not_connected / expired / error, the public YouTube channel id, expiry, when
  it was last verified, and a human-readable detail. There is no column that
  could hold a token, and there never will be.
- `credential_ref` on `channels` is a *reference*: which secret, which public
  channel. Also not a secret.

### Naming

For credential ref `finance`, the token is read from:

```
CHRONOS_YT_TOKEN_FINANCE
```

and written to `youtube_token_finance.json` on the runner. The default channel
with a blank ref keeps the existing `YOUTUBE_TOKEN_JSON` / `youtube_token.json`
path, so nothing about the production channel changes.

### Connecting a channel

```bash
python tools/connect_channel.py --channel extinct-world
python tools/connect_channel.py --list      # status of every channel
```

This opens Google's consent screen locally and writes the token to that
channel's file. It prints the file path and the secret name — **never the
token**. Copy the file's contents into the GitHub secret named above.

### Why there is no "Connect YouTube" button

An OAuth code exchange needs the client secret, and the resulting refresh token
must be stored where the *publisher* can read it. The publisher is a GitHub
Actions job reading repository secrets; the Command Center is a read-only
dashboard holding a Supabase anon key. A button there could not complete the
exchange without either shipping a client secret to the browser or giving the
web app permission to write repository secrets — both strictly worse than one
local command. The Add Channel flow therefore hands over instructions, and the
status it shows afterwards is what the bot reports, since the bot is the only
party that can see the credential.

---

## 4. The pipeline

One pipeline with a channel argument, not one pipeline per channel:

```bash
python main.py --channel extinct-world
python main.py                      # the default channel, exactly as before
```

`ChannelContext` flows into:

| Stage | What the channel supplies |
| --- | --- |
| `TopicManager` | its own queue, its own past videos, its own learned scores |
| `ScriptEngine` | language, target duration, content strategy, niche rules, visual style |
| `AudioMixer` | TTS provider and narrator voice (the voice is part of the segment cache key, so two channels never share a rendered segment) |
| `YouTubeUploader` | its own token and its own YouTube target |
| `IntelligencePoller` / `AnalyticsClient` | its own OAuth token, its own videos |
| `FeedbackEngine` / `PerformanceAnalyzer` | its own videos in, its own scores out |

**Visual style** reaches the screen through the per-section `keywords` the script
prompt produces, which is what the stock-footage search actually runs on. It is
deliberately not appended to every Pexels query — literal style words make stock
search worse, not better.

**The publish gate is unchanged.** `main.py` uploads exactly when it uploaded
before; `human_approved` remains an audit flag that gates nothing (see
`docs/AUTONOMY.md`). Phase 5 changed *which channel* an upload targets, not
*whether* it happens.

### The isolation rule that matters most

A non-default channel **never** falls back to the process-wide
`YOUTUBE_CHANNEL_ID`. Publishing Finance's video to History's channel because a
config field was blank would be worse than failing, so a channel with no target
of its own omits the field and uploads to whatever channel its own token owns.

---

## 5. Scheduling

`.github/workflows/daily_video.yml` wakes **hourly**. A cheap `resolve` job
(two pure-Python packages, not `requirements.txt`) asks the registry which
channels are due at this UTC hour and emits a matrix; the 23 hours a day that
resolve to nothing cost seconds and produce an empty matrix, which the video job
skips.

GitHub cron cannot read a database, so this is how a per-channel
`publish_hour_utc` becomes a real schedule without hardcoding anyone's hour into
the workflow file.

- `fail-fast: false` — a credential failure or a render crash on one channel
  never cancels another channel's video.
- `max-parallel: 1` — one ffmpeg render at a time on a 2-core runner.
- A PAUSED channel is never returned, so pausing in the Command Center is what
  actually stops it being scheduled.
- `tools/list_channels.py` **cannot fail open**: an unloadable registry falls
  back to the default channel rather than emitting an empty matrix that would
  silently stop production.

With only the default channel configured, exactly one video job runs per day at
15:00 UTC — unchanged.

### Adding a channel's token secret to the workflow

Actions secrets cannot be enumerated at runtime, so each channel's token secret
is listed explicitly in the `Run Chronos bot` step's `env:` — one line per
channel:

```yaml
CHRONOS_YT_TOKEN_FINANCE: ${{ secrets.CHRONOS_YT_TOKEN_FINANCE }}
```

The alternative, dumping `toJSON(secrets)` into a single env var, widens the leak
surface for every secret in the repository to save one line of YAML. An unset
secret is an empty string, which reports as `not_connected` — it never falls
back to another channel's token.

---

## 6. Command Center

- **Channel switcher** in the header writes a cookie and refreshes, so Server
  Components re-query scoped to that channel. It renders nothing when there is
  one channel or none.
- **Filtering is a view control, not a security boundary.** RLS decides what a
  logged-in user may read at all; the selection decides what they are looking at
  now. Neither substitutes for the other.
- **Realtime** applies the same rule to live inserts: while scoped, another
  channel's event is dropped rather than appended, and global (null-channel)
  events stay visible.
- **Channels page** (`/channels`) shows each channel's configuration, credential
  status and per-channel health, plus a cross-channel comparison. Health is per
  channel on purpose — one channel's expired token must not make all of Chronos
  read unhealthy — and with no evidence the tone is *idle*, never a green tick.
- **Add Channel** (`/channels/new`) creates the channel **PAUSED**, always. A
  human activates it after connecting YouTube.

### RLS

Migration 0001 adds one write capability, deliberately narrow:

- `channels` only — no data table gains a write policy, so a logged-in user
  still cannot insert a video, event, metric or score.
- **insert + update only, no delete.** A channel is retired by pausing it, which
  keeps its history intact and is reversible.
- `channels` holds no secret by construction, so this cannot expose a token.

Every new table keeps the same authenticated-read policy as the rest of the
schema. The anon key alone still reads nothing.

---

## 7. Applying the migration

```sql
-- Existing project: Supabase SQL editor -> paste -> Run
supabase/migrations/0001_multi_channel.sql
```

A fresh project needs only `supabase/schema.sql`, which now contains the same
statements inline. Both are idempotent; running either twice is safe.

There is **no drop, no rename, no type change and no delete** in the migration.
`channel_id` is added as `NOT NULL DEFAULT 'default'`, which on Postgres 11+ is a
catalog-only change that backfills every existing row to the default channel in
the same statement — that *is* the required backfill. It is reversible by
dropping the three new tables and the added columns.

Until it is applied, the Channels page says so plainly and the rest of the app
behaves exactly as it did before.

---

## 8. Deliberately not implemented

- **Autonomous publishing.** Unchanged from Phase 4: the publish gate is not
  wired, and this phase did not wire it.
- **Per-channel autonomy configuration.** The foundation exists (channels carry
  config the backend reads), but no autonomy setting is stored or honoured. That
  is the Step 2 decision described in `docs/AUTONOMY.md`.
- **Per-channel competitor lists.** `COMPETITOR_CHANNEL_IDS` is still one global
  env var; competitor and trending polling read public data with an API key and
  run once per poll, attributed to the channel that ran them.
- **Deleting a channel.** Pause it. Deletion would orphan videos, learning and
  history that the schema deliberately keeps.
