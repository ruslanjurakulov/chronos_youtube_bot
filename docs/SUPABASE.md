# Supabase setup — the Command Center data backbone

The Chronos bot runs fully local by default: its state lives in
`history/chronos.db`, which on the scheduled GitHub Actions runners exists only
for the life of one job. To power the real-time **Command Center** (the separate
Next.js app on Vercel) with **real** data, the bot mirrors that state into a
hosted Supabase Postgres project, and the dashboard reads (and live-subscribes
to) it.

Until you complete the steps below, everything keeps working — the mirror is a
**no-op** and nothing is exposed. This is the one manual, credential-bearing
step that only you can do.

## 1. Create the project
1. Sign in at <https://supabase.com> and create a new project (free tier is
   fine to start). Pick a region close to you.
2. Wait for it to finish provisioning.

## 2. Apply the schema
1. In the project, open **SQL Editor → New query**.
2. Paste the entire contents of [`supabase/schema.sql`](../supabase/schema.sql)
   and click **Run**. It is idempotent — safe to re-run after updates.
   This creates the tables, enables Realtime on the activity/score tables, and
   turns on Row Level Security so the data is readable only by a logged-in user.

## 3. Collect the keys
In **Project Settings → API**, copy:

| Value | Where it goes | Notes |
| --- | --- | --- |
| **Project URL** (`https://xxxx.supabase.co`) | `SUPABASE_URL` (bot) **and** the Command Center app | public |
| **service_role key** | `SUPABASE_SERVICE_KEY` (bot only) | **secret — server-side only, never ship to the browser.** Bypasses RLS to write. |
| **anon key** | the Command Center app only | public; RLS keeps it read-only and login-gated |

## 4. Give the bot the secrets
In the `chronos_youtube_bot` GitHub repo → **Settings → Secrets and variables →
Actions**, add:

- `SUPABASE_URL` = the Project URL
- `SUPABASE_SERVICE_KEY` = the service_role key

The daily intelligence poll (`.github/workflows/intelligence_poll.yml`) already
reads these; once set, its final pass mirrors state to Supabase automatically.
No code change needed.

## 5. Verify
- Trigger the **Intelligence Poll** workflow manually (Actions → Intelligence
  Poll → Run workflow). With the secrets set and at least one published video in
  the DB, the run log ends with `Supabase mirror complete: {...}`.
- In Supabase **Table Editor**, confirm rows appear in `system_events`,
  `videos`, `topic_performance`, etc.
- Locally you can dry-run the mirror without CI:
  ```bash
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python tools/run_intelligence_poll.py
  ```

## What gets mirrored
`modules/supabase_sync.py` upserts (idempotent — safe to re-run):

- `videos`, `metrics_snapshots` (latest per video), `competitor_snapshots`,
  `trending_snapshots`, `feedback_signals`, `topic_performance`
- `system_events` (the activity feed; upserted on a synthetic `event_key` so
  re-syncs never duplicate)

## Security
- RLS is **on** for every table with **no public read policy**, so the anon key
  alone reads nothing. The Command Center must authenticate a Supabase user.
- The bot writes with the service-role key (server-side, in GitHub Actions
  secrets — never in the browser bundle).
- The event stream never contains secrets: `modules/event_log.py` redacts
  credential-bearing metadata keys before they are ever stored.
