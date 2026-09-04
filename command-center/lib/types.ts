/**
 * Row shapes mirroring the Supabase tables (supabase/schema.sql at the repo
 * root), which in turn mirror the bot's SQLite state_store. Keep these in sync
 * with that schema.
 */

export interface VideoRow {
  video_id: string;
  topic: string | null;
  title: string | null;
  slug: string | null;
  published_at: string | null;
  privacy: string | null;
  category_id: string | null;
  local_path: string | null;
}

export interface MetricsSnapshotRow {
  video_id: string;
  snapshot_date: string;
  views: number | null;
  likes: number | null;
  comment_count: number | null;
  watch_time_minutes: number | null;
  average_view_duration_seconds: number | null;
}

export interface TopicPerformanceRow {
  topic: string;
  score: number;
  videos_analyzed: number;
  avg_views_per_day: number | null;
  reason: string | null;
  updated_at: string;
}

export interface FeedbackSignalRow {
  video_id: string;
  topic: string | null;
  signal: string;
  metric_value: number | null;
  channel_baseline: number | null;
  detail: string | null;
  analyzed_date: string;
}

export interface SystemEventRow {
  event_key: string;
  event: string;
  ts: string;
  video_id: string | null;
  job_id: string | null;
  agent: string | null;
  status: string | null;
  duration_ms: number | null;
  metadata: Record<string, unknown> | null;
}

export interface CompetitorSnapshotRow {
  video_id: string;
  channel_id: string;
  title: string | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  published_at: string | null;
  polled_date: string;
  view_velocity: number | null;
}

export interface DemandSignalRow {
  id: number;
  topic_phrase: string;
  mention_count: number;
  example_comment_ids: string | null;
  polled_date: string;
}

/**
 * Operational state mirrored for observability (Phase 4, step 1). These two
 * tables mirror what the bot already keeps under history/; nothing reads them
 * back into the pipeline and the publish path is unaffected.
 */
export interface ContentQueueRow {
  entry_id: string;
  topic: string;
  added_at: string;
  source: string | null;
  rationale: string | null;
  status: string;
  synced_at: string | null;
}

export interface PipelineRunStage {
  stage: string;
  timestamp: string;
  note?: string;
}

export interface PipelineRunRow {
  run_id: string;
  topic: string;
  current_stage: string;
  /** The audit-trail flag set by tools/approve_run.py. Nothing gates publishing on it. */
  human_approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
  history: PipelineRunStage[] | null;
  started_at: string | null;
  updated_at: string | null;
  synced_at: string | null;
}
