import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, StatCard, EmptyState, StatusPill } from "@/components/ui";
import { ViewsSparkline } from "@/components/videos/ViewsSparkline";
import { num, decimal, relativeTime, timeOfDay, statusTone } from "@/lib/format";
import type { MetricsSnapshotRow, SystemEventRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const TONE_COLOR: Record<string, string> = {
  ok: "var(--color-ok)",
  run: "var(--color-primary)",
  fail: "var(--color-fail)",
  idle: "var(--color-idle)",
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
        {label}
      </div>
      <div className="text-sm text-[var(--color-fg)] break-words">{value}</div>
    </div>
  );
}

export default async function VideoDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { id } = await params;

  const supabase = await createClient();
  let video: VideoRow | null = null;
  let snapshots: MetricsSnapshotRow[] = [];
  let events: SystemEventRow[] = [];

  if (supabase) {
    const [vid, snap, ev] = await Promise.all([
      supabase.from("videos").select("*").eq("video_id", id).maybeSingle(),
      supabase
        .from("metrics_snapshots")
        .select("*")
        .eq("video_id", id)
        .order("snapshot_date", { ascending: true }),
      supabase
        .from("system_events")
        .select("*")
        .eq("video_id", id)
        .order("ts", { ascending: true }),
    ]);
    video = (vid.data as VideoRow | null) ?? null;
    snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
    events = (ev.data as SystemEventRow[]) ?? [];
  }

  if (!video) {
    return (
      <div className="flex flex-col gap-4">
        <Link
          href="/videos"
          className="mono text-[11px] text-[var(--color-primary)] hover:underline"
        >
          ← Video Library
        </Link>
        <Panel title="Video Not Found">
          <EmptyState>
            No video with id <span className="mono text-[var(--color-fg)]">{id}</span> exists in the
            library.
          </EmptyState>
        </Panel>
      </div>
    );
  }

  const latest = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <Link
            href="/videos"
            className="mono text-[11px] text-[var(--color-primary)] hover:underline"
          >
            ← Video Library
          </Link>
          <h1 className="mt-1 truncate text-lg font-semibold">{video.title ?? video.video_id}</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            {video.topic ?? "no topic"} · published {relativeTime(video.published_at)}
          </p>
        </div>
        <StatusPill
          tone={video.privacy === "public" ? "ok" : "idle"}
          label={(video.privacy ?? "unknown").toUpperCase()}
        />
      </div>

      <Panel title="Content">
        <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Title" value={video.title ?? "N/A"} />
          <Field label="Topic" value={video.topic ?? "N/A"} />
          <Field label="Slug" value={video.slug ?? "N/A"} />
          <Field label="Privacy" value={video.privacy ?? "N/A"} />
          <Field
            label="Published"
            value={
              video.published_at ? (
                <span className="mono text-[13px]">{video.published_at}</span>
              ) : (
                "N/A"
              )
            }
          />
          <Field
            label="Video ID"
            value={<span className="mono text-[13px]">{video.video_id}</span>}
          />
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Pipeline">
          {events.length === 0 ? (
            <EmptyState>No pipeline events recorded for this video yet.</EmptyState>
          ) : (
            <ol className="divide-y divide-[var(--color-border)]">
              {events.map((e) => {
                const tone = statusTone(e.status);
                return (
                  <li key={e.event_key} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    <span className="mono w-16 shrink-0 text-[10px] text-[var(--color-muted)]">
                      {timeOfDay(e.ts)}
                    </span>
                    <span
                      className="glow-dot size-1.5 shrink-0 rounded-full"
                      style={{ color: TONE_COLOR[tone], background: TONE_COLOR[tone] }}
                    />
                    <span className="mono shrink-0 text-[11px] text-[var(--color-primary)]">
                      {e.agent ?? "system"}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[var(--color-fg)]">
                      {e.event}
                    </span>
                    {e.status && (
                      <span
                        className="mono shrink-0 text-[10px] uppercase tracking-wider"
                        style={{ color: TONE_COLOR[tone] }}
                      >
                        {e.status}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </Panel>

        <Panel title="Analytics">
          {latest === null ? (
            <EmptyState>
              No metrics snapshots yet. Analytics appear once the bot polls YouTube for this video.
            </EmptyState>
          ) : (
            <div className="flex flex-col gap-4 p-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard label="Views" value={num(latest.views)} tone="ok" />
                <StatCard label="Likes" value={num(latest.likes)} />
                <StatCard label="Comments" value={num(latest.comment_count)} />
                <StatCard
                  label="Watch time (min)"
                  value={decimal(latest.watch_time_minutes)}
                />
                <StatCard
                  label="Avg view (s)"
                  value={decimal(latest.average_view_duration_seconds)}
                />
                <StatCard
                  label="Snapshots"
                  value={num(snapshots.length)}
                  sub={`latest ${relativeTime(latest.snapshot_date)}`}
                />
              </div>

              {snapshots.length >= 2 && (
                <div className="flex flex-col gap-2">
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                    Views over time
                  </div>
                  <ViewsSparkline
                    points={snapshots.map((s) => ({
                      date: s.snapshot_date,
                      views: s.views,
                    }))}
                  />
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
