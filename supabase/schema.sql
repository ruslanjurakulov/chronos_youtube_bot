-- Chronos Command Center — Supabase (Postgres) schema
-- ============================================================================
-- Apply this ONCE to a fresh Supabase project (SQL Editor -> paste -> Run),
-- then set SUPABASE_URL + SUPABASE_SERVICE_KEY as GitHub Actions secrets so the
-- Python bot (modules/supabase_sync.py) mirrors its state here, and set the URL
-- + anon key in the Command Center app so it can read/subscribe. See
-- docs/SUPABASE.md for the full walkthrough.
--
-- These tables mirror modules/state_store.py's SQLite schema 1:1 (plus an
-- event_key on system_events for idempotent re-sync). Column names and the
-- UNIQUE constraints match the on_conflict targets in supabase_sync.py exactly
-- — do not rename without updating that module.
--
-- Security (brief §24): Row Level Security is ON for every table with NO public
-- policy, so the anon key alone can read NOTHING. The bot writes with the
-- service-role key (which bypasses RLS). The Command Center reads only for a
-- logged-in Supabase user via the "authenticated read" policies below — so the
-- monitoring data is never publicly accessible.

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table if not exists public.videos (
    video_id     text primary key,
    topic        text,
    title        text,
    slug         text,
    published_at text,
    privacy      text,
    category_id  text,
    local_path   text
);

create table if not exists public.metrics_snapshots (
    video_id                       text not null,
    snapshot_date                  text not null,
    views                          integer,
    likes                          integer,
    comment_count                  integer,
    watch_time_minutes             double precision,
    average_view_duration_seconds  double precision,
    unique (video_id, snapshot_date)
);
create index if not exists idx_metrics_video_date on public.metrics_snapshots (video_id, snapshot_date);

create table if not exists public.competitor_snapshots (
    video_id       text not null,
    channel_id     text not null,
    title          text,
    view_count     integer,
    like_count     integer,
    comment_count  integer,
    published_at   text,
    polled_date    text not null,
    view_velocity  double precision,
    unique (video_id, polled_date)
);
create index if not exists idx_competitor_channel_date on public.competitor_snapshots (channel_id, polled_date);

create table if not exists public.trending_snapshots (
    video_id       text not null,
    title          text,
    view_count     integer,
    like_count     integer,
    comment_count  integer,
    published_at   text,
    region_code    text,
    category_id    text,
    polled_date    text not null,
    unique (video_id, polled_date, region_code)
);
create index if not exists idx_trending_date on public.trending_snapshots (polled_date);

create table if not exists public.demand_signals (
    id                  bigint generated always as identity primary key,
    topic_phrase        text not null,
    mention_count       integer not null,
    example_comment_ids text,
    polled_date         text not null
);
create index if not exists idx_demand_date on public.demand_signals (polled_date);

create table if not exists public.feedback_signals (
    video_id         text not null,
    topic            text,
    signal           text not null,
    metric_value     double precision,
    channel_baseline double precision,
    detail           text,
    analyzed_date    text not null,
    unique (video_id, signal, analyzed_date)
);
create index if not exists idx_feedback_date on public.feedback_signals (analyzed_date);

create table if not exists public.topic_performance (
    topic             text primary key,
    score             double precision not null,
    videos_analyzed   integer not null,
    avg_views_per_day double precision,
    reason            text,
    updated_at        text not null
);

create table if not exists public.system_events (
    event_key    text primary key,
    event        text not null,
    ts           text not null,
    video_id     text,
    job_id       text,
    agent        text,
    status       text,
    duration_ms  double precision,
    metadata     jsonb
);
create index if not exists idx_events_ts on public.system_events (ts desc);
create index if not exists idx_events_video on public.system_events (video_id);

-- ---------------------------------------------------------------------------
-- Realtime — let the Command Center live-subscribe to the activity feed
-- ---------------------------------------------------------------------------
-- Adds the event + score tables to the supabase_realtime publication so the
-- dashboard receives inserts/updates over websockets with no polling.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    execute 'alter publication supabase_realtime add table public.system_events';
    execute 'alter publication supabase_realtime add table public.topic_performance';
    execute 'alter publication supabase_realtime add table public.metrics_snapshots';
  end if;
exception when duplicate_object then
  null;  -- already in the publication; ignore
end $$;

-- ---------------------------------------------------------------------------
-- Row Level Security — read only for logged-in users; writes via service key
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'videos','metrics_snapshots','competitor_snapshots','trending_snapshots',
    'demand_signals','feedback_signals','topic_performance','system_events'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    -- Drop-and-recreate so re-running this file is idempotent.
    execute format('drop policy if exists %I on public.%I', t || '_auth_read', t);
    execute format(
      'create policy %I on public.%I for select to authenticated using (true)',
      t || '_auth_read', t
    );
  end loop;
end $$;

-- Note: the service-role key used by the bot bypasses RLS, so no INSERT/UPDATE
-- policies are needed for the sync. The anon key has no policy and therefore no
-- access — the Command Center must authenticate a user to read anything.
