import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, EmptyState, StatCard } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import type { FeedbackSignalRow, TopicPerformanceRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const LOOP = [
  "Published video",
  "Collect analytics",
  "Analyze performance",
  "Learning signal",
  "Topic score",
  "Topic Manager",
  "Next video",
];

function signalTone(signal: string): string {
  if (signal.startsWith("HIGH_")) return "var(--color-ok)";
  if (signal.startsWith("LOW_")) return "var(--color-fail)";
  return "var(--color-muted)";
}

export default async function FeedbackPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let signals: FeedbackSignalRow[] = [];
  let topics: TopicPerformanceRow[] = [];

  if (supabase) {
    const [sg, tp] = await Promise.all([
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(200),
      supabase.from("topic_performance").select("*").order("score", { ascending: false }).limit(50),
    ]);
    signals = (sg.data as FeedbackSignalRow[]) ?? [];
    topics = (tp.data as TopicPerformanceRow[]) ?? [];
  }

  const lastRun = signals[0]?.analyzed_date ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">Feedback Loop</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">
          Real published-video performance turned into learning that steers the next topic
        </p>
      </div>

      {/* The loop, drawn from the real stages the backend runs */}
      <div className="panel overflow-x-auto p-4">
        <div className="flex min-w-max items-center gap-2">
          {LOOP.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <span className="mono whitespace-nowrap rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2.5 py-1.5 text-[11px] text-[var(--color-fg)]">
                {step}
              </span>
              {i < LOOP.length - 1 && <span className="text-[var(--color-primary)]">→</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Scored topics" value={topics.length} tone={topics.length ? "run" : "idle"} />
        <StatCard label="Signals recorded" value={signals.length} sub="most recent analysis" />
        <StatCard label="Last analysis" value={lastRun ? relativeTime(lastRun) : "—"} sub={lastRun ?? "not run yet"} />
        <StatCard
          label="Above avg"
          value={topics.filter((t) => t.score >= 50).length}
          tone="ok"
          sub={`of ${topics.length} topics`}
        />
      </div>

      <Panel title="Learned Topic Scores — and why">
        {topics.length === 0 ? (
          <EmptyState>
            The loop hasn&apos;t produced scores yet — it needs ≥2 published videos with metrics before a
            channel average exists to compare against.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">Topic</th>
                  <th className="px-4 py-2 font-semibold">Score</th>
                  <th className="px-4 py-2 font-semibold">Videos</th>
                  <th className="px-4 py-2 font-semibold">Reason (from real ratios)</th>
                  <th className="px-4 py-2 font-semibold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {topics.map((t) => (
                  <tr key={t.topic} className="border-b border-[var(--color-border)]/50">
                    <td className="px-4 py-2 text-[var(--color-fg)]">{t.topic}</td>
                    <td className="px-4 py-2 mono font-bold tabular-nums"
                      style={{ color: t.score >= 50 ? "var(--color-ok)" : "var(--color-warn)" }}>
                      {t.score.toFixed(0)}
                    </td>
                    <td className="px-4 py-2 mono text-[var(--color-muted)] tabular-nums">{t.videos_analyzed}</td>
                    <td className="px-4 py-2 text-[11px] text-[var(--color-muted)]">{t.reason ?? "—"}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{relativeTime(t.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Recent Performance Signals">
        {signals.length === 0 ? (
          <EmptyState>No learning signals recorded yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">Signal</th>
                  <th className="px-4 py-2 font-semibold">Topic</th>
                  <th className="px-4 py-2 font-semibold">Video</th>
                  <th className="px-4 py-2 font-semibold">Detail</th>
                  <th className="px-4 py-2 font-semibold">Analyzed</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={`${s.video_id}-${s.signal}-${i}`} className="border-b border-[var(--color-border)]/50">
                    <td className="px-4 py-2 mono text-[11px] font-semibold" style={{ color: signalTone(s.signal) }}>
                      {s.signal}
                    </td>
                    <td className="px-4 py-2 text-[var(--color-muted)]">{s.topic ?? "—"}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{s.video_id}</td>
                    <td className="px-4 py-2 text-[11px] text-[var(--color-muted)]">{s.detail ?? "—"}</td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">{relativeTime(s.analyzed_date)}</td>
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
