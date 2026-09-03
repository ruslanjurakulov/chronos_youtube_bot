import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { StatCard, Panel, EmptyState, StatusPill } from "@/components/ui";
import { ActivityFeed } from "@/components/ActivityFeed";
import { isToday, num, relativeTime, statusTone } from "@/lib/format";
import type { SystemEventRow, TopicPerformanceRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DAY_MS = 24 * 60 * 60 * 1000;

export default async function CommandCenter() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let videos: VideoRow[] = [];
  let topics: TopicPerformanceRow[] = [];
  let dbHealthy = true;

  if (supabase) {
    const sinceDay = new Date(Date.now() - DAY_MS).toISOString();
    const [ev, vid, tp] = await Promise.all([
      supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(60),
      supabase.from("videos").select("*").order("published_at", { ascending: false }).limit(8),
      supabase.from("topic_performance").select("*").order("score", { ascending: false }).limit(6),
    ]);
    if (ev.error || vid.error || tp.error) dbHealthy = false;
    events = (ev.data as SystemEventRow[]) ?? [];
    videos = (vid.data as VideoRow[]) ?? [];
    topics = (tp.data as TopicPerformanceRow[]) ?? [];
    void sinceDay;
  }

  const publishedToday = videos.filter((v) => isToday(v.published_at)).length;
  const errors24h = events.filter(
    (e) => statusTone(e.status) === "fail" && Date.now() - new Date(e.ts).getTime() < DAY_MS,
  ).length;
  const runningAgents = Array.from(
    new Set(events.filter((e) => statusTone(e.status) === "run").map((e) => e.agent)),
  ).filter(Boolean);
  const lastEventAt = events[0]?.ts ?? null;
  const healthy = dbHealthy && errors24h === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Command Center</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Real-time state of the content-automation pipeline
          </p>
        </div>
        <StatusPill tone={healthy ? "ok" : errors24h > 0 ? "fail" : "run"}
          label={healthy ? "SYSTEM HEALTHY" : errors24h > 0 ? "ATTENTION" : "ACTIVE"} />
      </div>

      {/* Top stat row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="System" value={healthy ? "OK" : "CHECK"} tone={healthy ? "ok" : "warn"}
          sub={lastEventAt ? `last event ${relativeTime(lastEventAt)}` : "no events yet"} />
        <StatCard label="Published today" value={publishedToday} tone="ok" sub="videos live" />
        <StatCard label="Active agents" value={runningAgents.length} tone={runningAgents.length ? "run" : "idle"}
          sub={runningAgents.length ? runningAgents.join(", ") : "idle"} />
        <StatCard label="Errors (24h)" value={errors24h} tone={errors24h ? "fail" : "ok"}
          sub={errors24h ? "needs attention" : "none"} />
        <StatCard label="Videos" value={num(videos.length >= 8 ? undefined : videos.length)}
          sub={videos.length >= 8 ? "showing latest 8" : "in library"} />
        <StatCard label="Database" value={dbHealthy ? "HEALTHY" : "ERROR"} tone={dbHealthy ? "ok" : "fail"}
          sub="Supabase" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Live activity feed (realtime) */}
        <div className="lg:col-span-2">
          <Panel title="Live Activity Feed">
            <div className="h-[420px]">
              <ActivityFeed initial={events} />
            </div>
          </Panel>
        </div>

        {/* Learned topic scores (feedback loop output) */}
        <Panel title="Top Topic Scores">
          {topics.length === 0 ? (
            <EmptyState>No scored topics yet — the feedback loop needs ≥2 published videos with metrics.</EmptyState>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {topics.map((t) => (
                <li key={t.topic} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-[var(--color-fg)]">{t.topic}</div>
                    <div className="truncate mono text-[10px] text-[var(--color-muted)]">{t.reason}</div>
                  </div>
                  <div
                    className="mono shrink-0 text-lg font-bold tabular-nums"
                    style={{ color: t.score >= 50 ? "var(--color-ok)" : "var(--color-warn)" }}
                  >
                    {t.score.toFixed(0)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {/* Recent videos */}
      <Panel title="Recent Videos">
        {videos.length === 0 ? (
          <EmptyState>No videos yet. Once the bot publishes, they appear here with live metrics.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">Title</th>
                  <th className="px-4 py-2 font-semibold">Topic</th>
                  <th className="px-4 py-2 font-semibold">Published</th>
                  <th className="px-4 py-2 font-semibold">Privacy</th>
                </tr>
              </thead>
              <tbody>
                {videos.map((v) => (
                  <tr key={v.video_id} className="border-b border-[var(--color-border)]/50">
                    <td className="px-4 py-2 text-[var(--color-fg)]">{v.title ?? v.video_id}</td>
                    <td className="px-4 py-2 text-[var(--color-muted)]">{v.topic ?? "—"}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">
                      {relativeTime(v.published_at)}
                    </td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{v.privacy ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
