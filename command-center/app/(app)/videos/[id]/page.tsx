import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, StatCard, EmptyState, StatusPill } from "@/components/ui";
import { ViewsSparkline } from "@/components/videos/ViewsSparkline";
import { VideoLifecycle } from "@/components/videos/VideoLifecycle";
import { IntelligenceTrace } from "@/components/intel/IntelligenceTrace";
import { QualityGate } from "@/components/autonomy/QualityGate";
import { buildTrace } from "@/lib/decisions";
import { num, decimal, relativeTime, timeOfDay, statusTone } from "@/lib/format";
import { getDictionary } from "@/lib/i18n/server";
import { fetchChannelTopicScores } from "@/lib/channels-server";
import { fmt } from "@/lib/i18n";
import type { FeedbackSignalRow, MetricsSnapshotRow, SystemEventRow, TopicPerformanceRow, VideoRow } from "@/lib/types";

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
      <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
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
  const { t } = await getDictionary();

  const supabase = await createClient();
  let video: VideoRow | null = null;
  let snapshots: MetricsSnapshotRow[] = [];
  let events: SystemEventRow[] = [];
  let learningSignals: FeedbackSignalRow[] = [];
  let topicPerf: TopicPerformanceRow[] = [];

  if (supabase) {
    const [vid, snap, ev, fs] = await Promise.all([
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
      supabase.from("feedback_signals").select("*").eq("video_id", id).limit(50),
    ]);
    video = (vid.data as VideoRow | null) ?? null;
    snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
    events = (ev.data as SystemEventRow[]) ?? [];
    learningSignals = (fs.data as FeedbackSignalRow[]) ?? [];
    // Scored against its OWN channel, not the switcher: a link to a video is
    // valid whatever channel is selected, and the score that explains this
    // video is the one its channel learned.
    if (video) {
      topicPerf = await fetchChannelTopicScores(supabase, video.channel_id);
    }
  }

  if (!video) {
    return (
      <div className="rhythm stagger-enter">
        <Link
          href="/videos"
          className="mono text-[11px] text-[var(--color-primary)] hover:underline"
        >
          {t.videoDetail.back}
        </Link>
        <Panel title={t.videoDetail.notFound}>
          <EmptyState>
            {t.videoDetail.notFoundBodyA} <span className="mono text-[var(--color-fg)]">{id}</span>{" "}
            {t.videoDetail.notFoundBodyB}
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
            {t.videoDetail.back}
          </Link>
          <h1 className="t-hero mt-2 truncate">{video.title ?? video.video_id}</h1>
          <p className="t-lead mt-4">
            {video.topic ?? t.videoDetail.noTopic} · {fmt(t.videoDetail.published, { t: relativeTime(video.published_at) })}
          </p>
        </div>
        <StatusPill
          tone={video.privacy === "public" ? "ok" : "idle"}
          label={(video.privacy ?? t.videoDetail.unknown).toUpperCase()}
        />
      </div>

      <Panel title={t.videoDetail.content}>
        <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t.videoDetail.fTitle} value={video.title ?? t.common.na} />
          <Field label={t.videoDetail.fTopic} value={video.topic ?? t.common.na} />
          <Field label={t.videoDetail.fSlug} value={video.slug ?? t.common.na} />
          <Field label={t.videoDetail.fPrivacy} value={video.privacy ?? t.common.na} />
          <Field
            label={t.videoDetail.fPublished}
            value={
              video.published_at ? (
                <span className="mono text-[13px]">{video.published_at}</span>
              ) : (
                t.common.na
              )
            }
          />
          <Field
            label={t.videoDetail.fVideoId}
            value={<span className="mono text-[13px]">{video.video_id}</span>}
          />
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={t.auto.gateTitle}>
        <QualityGate events={events} />
      </Panel>

      <Panel title={t.ops.lifecycleTitle}>
          <VideoLifecycle events={events} hasMetrics={snapshots.length > 0} hasLearning={learningSignals.length > 0} />
        </Panel>
        <Panel title={t.intel.traceTitle}>
          <IntelligenceTrace
            steps={buildTrace(
              video.video_id,
              video.topic,
              events,
              snapshots.length,
              learningSignals,
              topicPerf.find((p) => p.topic === video.topic) ?? null,
            )}
          />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={t.videoDetail.pipeline}>
          {events.length === 0 ? (
            <EmptyState>{t.videoDetail.noPipeline}</EmptyState>
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
                      {e.agent ?? t.common.system}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[var(--color-fg)]">
                      {e.event}
                    </span>
                    {e.status && (
                      <span
                        className="shrink-0 text-[10px] uppercase tracking-[0.22em]"
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

        <Panel title={t.videoDetail.analytics}>
          {latest === null ? (
            <EmptyState>{t.videoDetail.noAnalytics}</EmptyState>
          ) : (
            <div className="flex flex-col gap-4 p-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard label={t.videoDetail.views} value={num(latest.views)} tone="ok" />
                <StatCard label={t.videoDetail.likes} value={num(latest.likes)} />
                <StatCard label={t.videoDetail.comments} value={num(latest.comment_count)} />
                <StatCard
                  label={t.videoDetail.watchTime}
                  value={decimal(latest.watch_time_minutes)}
                />
                <StatCard
                  label={t.videoDetail.avgView}
                  value={decimal(latest.average_view_duration_seconds)}
                />
                <StatCard
                  label={t.videoDetail.snapshots}
                  value={num(snapshots.length)}
                  sub={fmt(t.videoDetail.latestT, { t: relativeTime(latest.snapshot_date) })}
                />
              </div>

              {snapshots.length >= 2 && (
                <div className="flex flex-col gap-2">
                  <div className="text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
                    {t.videoDetail.viewsOverTime}
                  </div>
                  <ViewsSparkline
                    label={t.videoDetail.viewsOverTime}
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
