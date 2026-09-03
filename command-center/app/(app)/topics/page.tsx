import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, StatCard, EmptyState } from "@/components/ui";
import { num, decimal, relativeTime } from "@/lib/format";
import type { DemandSignalRow, TopicPerformanceRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function TopicManager() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let topics: TopicPerformanceRow[] = [];
  let demand: DemandSignalRow[] = [];
  let dbError = false;

  if (supabase) {
    const [tp, ds] = await Promise.all([
      supabase.from("topic_performance").select("*").order("score", { ascending: false }),
      supabase
        .from("demand_signals")
        .select("*")
        .order("polled_date", { ascending: false })
        .limit(50),
    ]);
    if (tp.error || ds.error) dbError = true;
    topics = (tp.data as TopicPerformanceRow[]) ?? [];
    demand = (ds.data as DemandSignalRow[]) ?? [];
  }

  const scored = topics.length;
  const strong = topics.filter((t) => t.score >= 50).length;
  const topScore = topics.length > 0 ? topics[0].score : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Topic Manager</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Learned topic scores from the feedback loop and live audience demand
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label="Topics scored" value={num(scored)} sub="in the feedback loop" />
        <StatCard
          label="Strong topics"
          value={num(strong)}
          tone="ok"
          sub="score ≥ 50"
        />
        <StatCard
          label="Top score"
          value={topScore === null ? "N/A" : topScore.toFixed(0)}
          tone={topScore !== null && topScore >= 50 ? "ok" : "warn"}
          sub="highest ranked"
        />
      </div>

      <Panel title="Topic Scores">
        {dbError ? (
          <EmptyState>Could not read topic performance from Supabase.</EmptyState>
        ) : topics.length === 0 ? (
          <EmptyState>
            No topic has been scored yet — the feedback loop needs ≥2 published videos with metrics.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">Topic</th>
                  <th className="px-4 py-2 text-right font-semibold">Score</th>
                  <th className="px-4 py-2 text-right font-semibold">Videos</th>
                  <th className="px-4 py-2 text-right font-semibold">Avg views/day</th>
                  <th className="px-4 py-2 font-semibold">Reason</th>
                  <th className="px-4 py-2 font-semibold">Updated</th>
                </tr>
              </thead>
              <tbody>
                {topics.map((t) => (
                  <tr key={t.topic} className="border-b border-[var(--color-border)]/50">
                    <td className="px-4 py-2 text-[var(--color-fg)]">{t.topic}</td>
                    <td
                      className="px-4 py-2 text-right mono font-bold tabular-nums"
                      style={{
                        color: t.score >= 50 ? "var(--color-ok)" : "var(--color-warn)",
                      }}
                    >
                      {t.score.toFixed(0)}
                    </td>
                    <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                      {num(t.videos_analyzed)}
                    </td>
                    <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                      {decimal(t.avg_views_per_day)}
                    </td>
                    <td className="px-4 py-2 max-w-xs truncate text-[var(--color-muted)]">
                      {t.reason ?? "N/A"}
                    </td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">
                      {relativeTime(t.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Audience Demand">
        {demand.length === 0 ? (
          <EmptyState>
            No demand signals yet — these are topic phrases mined from audience comments.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {demand.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between gap-3 px-4 py-2.5"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-[var(--color-fg)]">{d.topic_phrase}</div>
                  <div className="mono text-[10px] text-[var(--color-muted)]">
                    polled {relativeTime(d.polled_date)}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="mono text-lg font-bold tabular-nums text-[var(--color-primary)]">
                    {num(d.mention_count)}
                  </div>
                  <div className="mono text-[9px] uppercase tracking-widest text-[var(--color-muted)]">
                    mentions
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
