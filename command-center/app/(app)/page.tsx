import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { StatCard, EmptyState, StatusPill } from "@/components/ui";
import { ActivityFeed } from "@/components/ActivityFeed";
import { AnimatedNumber } from "@/components/AnimatedNumber";
import { ChronosCore } from "@/components/ChronosCore";
import { SystemStatus } from "@/components/SystemStatus";
import { DailyMission } from "@/components/DailyMission";
import { NextAction } from "@/components/NextAction";
import { Widget } from "@/components/dashboard/Widget";
import { CustomizeButton } from "@/components/dashboard/CustomizeButton";
import { isToday, num, relativeTime, statusTone } from "@/lib/format";
import { inferNextStage, dailyMission } from "@/lib/intelligence";
import { getDictionary } from "@/lib/i18n/server";
import { fmt } from "@/lib/i18n";
import type { FeedbackSignalRow, MetricsSnapshotRow, SystemEventRow, TopicPerformanceRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DAY_MS = 24 * 60 * 60 * 1000;

export default async function CommandCenter() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let videos: VideoRow[] = [];
  let topics: TopicPerformanceRow[] = [];
  let snapshots: MetricsSnapshotRow[] = [];
  let signals: FeedbackSignalRow[] = [];
  let dbHealthy = true;

  if (supabase) {
    const [ev, vid, tp, snap, sg] = await Promise.all([
      supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(200),
      supabase.from("videos").select("*").order("published_at", { ascending: false }).limit(50),
      supabase.from("topic_performance").select("*").order("score", { ascending: false }).limit(6),
      supabase.from("metrics_snapshots").select("*").order("snapshot_date", { ascending: false }).limit(200),
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(200),
    ]);
    if (ev.error || vid.error || tp.error) dbHealthy = false;
    events = (ev.data as SystemEventRow[]) ?? [];
    videos = (vid.data as VideoRow[]) ?? [];
    topics = (tp.data as TopicPerformanceRow[]) ?? [];
    snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
    signals = (sg.data as FeedbackSignalRow[]) ?? [];
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
  const recentVideos = videos.slice(0, 8);
  const mission = dailyMission(videos, snapshots, signals);
  const next = inferNextStage(events);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">{t.dashboard.title}</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">{t.dashboard.subtitle}</p>
        </div>
        <div className="flex items-center gap-3">
          <CustomizeButton />
          <StatusPill
            tone={healthy ? "ok" : errors24h > 0 ? "fail" : "run"}
            label={healthy ? t.dashboard.systemHealthy : errors24h > 0 ? t.dashboard.attention : t.dashboard.active}
            live={healthy}
          />
        </div>
      </div>

      {/* Hero band — Chronos Core + real system status + today's mission */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel flex items-center justify-center p-5">
          <ChronosCore initial={events} size={200} />
        </div>
        <Widget id="status" title={t.ops.statusTitle}>
          <SystemStatus initial={events} dbOk={dbHealthy} />
        </Widget>
        <Widget id="mission" title={t.ops.missionTitle}>
          <DailyMission
            publishedToday={mission.publishedToday}
            analyticsToday={mission.analyticsToday}
            learningToday={mission.learningToday}
          />
        </Widget>
      </div>

      {/* Top stat row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label={t.dashboard.system} value={healthy ? t.dashboard.valOk : t.dashboard.valCheck} tone={healthy ? "ok" : "warn"}
          sub={lastEventAt ? fmt(t.dashboard.lastEvent, { t: relativeTime(lastEventAt) }) : t.dashboard.noEvents} />
        <StatCard label={t.dashboard.publishedToday} value={<AnimatedNumber value={publishedToday} />} tone="ok" sub={t.dashboard.videosLive} />
        <StatCard label={t.dashboard.activeAgents} value={<AnimatedNumber value={runningAgents.length} />} tone={runningAgents.length ? "run" : "idle"}
          sub={runningAgents.length ? runningAgents.join(", ") : t.common.idle} />
        <StatCard label={t.dashboard.errors24h} value={<AnimatedNumber value={errors24h} />} tone={errors24h ? "fail" : "ok"}
          sub={errors24h ? t.dashboard.needsAttention : t.common.none} />
        <StatCard label={t.dashboard.videos} value={num(videos.length >= 8 ? undefined : videos.length)}
          sub={videos.length >= 8 ? t.dashboard.showingLatest8 : t.dashboard.inLibrary} />
        <StatCard label={t.dashboard.database} value={dbHealthy ? t.dashboard.dbHealthy : t.dashboard.dbError} tone={dbHealthy ? "ok" : "fail"}
          sub={t.dashboard.supabase} />
      </div>

      {/* Next action (inferred from real in-flight pipeline state) */}
      <Widget id="next" title={t.ops.nextTitle}>
        <NextAction next={next} />
      </Widget>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Live activity feed (realtime) */}
        <Widget id="feed" title={t.ops.streamTitle} span="lg:col-span-2">
          <div className="h-[420px]">
            <ActivityFeed initial={events} />
          </div>
        </Widget>

        {/* Learned topic scores (feedback loop output) */}
        <Widget id="topics" title={t.dashboard.topTopics}>
          {topics.length === 0 ? (
            <EmptyState>{t.dashboard.noTopics}</EmptyState>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {topics.map((tp) => (
                <li key={tp.topic} className="flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-[var(--color-panel-2)]">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-[var(--color-fg)]">{tp.topic}</div>
                    <div className="truncate mono text-[10px] text-[var(--color-muted)]">{tp.reason}</div>
                  </div>
                  <div
                    className="mono shrink-0 text-lg font-bold tabular-nums"
                    style={{ color: tp.score >= 50 ? "var(--color-ok)" : "var(--color-warn)" }}
                  >
                    {tp.score.toFixed(0)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Widget>
      </div>

      {/* Recent videos */}
      <Widget id="videos" title={t.dashboard.recentVideos}>
        {recentVideos.length === 0 ? (
          <EmptyState>{t.dashboard.noVideos}</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">{t.dashboard.thTitle}</th>
                  <th className="px-4 py-2 font-semibold">{t.dashboard.thTopic}</th>
                  <th className="px-4 py-2 font-semibold">{t.dashboard.thPublished}</th>
                  <th className="px-4 py-2 font-semibold">{t.dashboard.thPrivacy}</th>
                </tr>
              </thead>
              <tbody>
                {recentVideos.map((v) => (
                  <tr key={v.video_id} className="border-b border-[var(--color-border)]/50 transition-colors hover:bg-[var(--color-panel-2)]">
                    <td className="px-4 py-2 text-[var(--color-fg)]">{v.title ?? v.video_id}</td>
                    <td className="px-4 py-2 text-[var(--color-muted)]">{v.topic ?? t.common.dash}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{relativeTime(v.published_at)}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{v.privacy ?? t.common.dash}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Widget>
    </div>
  );
}
