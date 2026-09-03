import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { StatCard, Panel, EmptyState } from "@/components/ui";
import { VideoTable } from "@/components/videos/VideoTable";
import { isToday, num } from "@/lib/format";
import type { MetricsSnapshotRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export interface VideoWithMetrics extends VideoRow {
  metrics: MetricsSnapshotRow | null;
}

export default async function VideoLibrary() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let videos: VideoRow[] = [];
  let snapshots: MetricsSnapshotRow[] = [];
  let dbError = false;

  if (supabase) {
    const vid = await supabase
      .from("videos")
      .select("*")
      .order("published_at", { ascending: false })
      .limit(100);
    if (vid.error) dbError = true;
    videos = (vid.data as VideoRow[]) ?? [];

    const ids = videos.map((v) => v.video_id);
    if (ids.length > 0) {
      const snap = await supabase
        .from("metrics_snapshots")
        .select("*")
        .in("video_id", ids)
        .order("snapshot_date", { ascending: false });
      if (snap.error) dbError = true;
      snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
    }
  }

  // Latest snapshot per video_id: snapshots are ordered snapshot_date desc, so
  // the first one seen for each video_id is the most recent.
  const latestByVideo = new Map<string, MetricsSnapshotRow>();
  for (const s of snapshots) {
    if (!latestByVideo.has(s.video_id)) latestByVideo.set(s.video_id, s);
  }

  const rows: VideoWithMetrics[] = videos.map((v) => ({
    ...v,
    metrics: latestByVideo.get(v.video_id) ?? null,
  }));

  const totalViews = rows.reduce((sum, r) => sum + (r.metrics?.views ?? 0), 0);
  const hasAnyViews = rows.some((r) => r.metrics?.views != null);
  const publishedToday = rows.filter((r) => isToday(r.published_at)).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Video Library</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Every published video with its latest metrics snapshot
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label="Videos shown" value={num(rows.length)} sub="latest 100" />
        <StatCard
          label="Total views"
          value={hasAnyViews ? num(totalViews) : "N/A"}
          tone="ok"
          sub="across shown videos"
        />
        <StatCard
          label="Published today"
          value={num(publishedToday)}
          tone="ok"
          sub="videos live"
        />
      </div>

      <Panel title="Library">
        {dbError ? (
          <EmptyState>Could not read the library from Supabase.</EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState>
            No videos yet. Once the bot publishes, they appear here with live metrics.
          </EmptyState>
        ) : (
          <VideoTable rows={rows} />
        )}
      </Panel>
    </div>
  );
}
