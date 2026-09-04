import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, StatCard, EmptyState } from "@/components/ui";
import { AnimatedNumber } from "@/components/AnimatedNumber";
import { ExplainScore } from "@/components/topics/ExplainScore";
import { num, decimal, relativeTime } from "@/lib/format";
import { getDictionary } from "@/lib/i18n/server";
import { fmt } from "@/lib/i18n";
import type { DemandSignalRow, FeedbackSignalRow, TopicPerformanceRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function TopicManager() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let topics: TopicPerformanceRow[] = [];
  let demand: DemandSignalRow[] = [];
  let signals: FeedbackSignalRow[] = [];
  let dbError = false;

  if (supabase) {
    const [tp, ds, fs] = await Promise.all([
      supabase.from("topic_performance").select("*").order("score", { ascending: false }),
      supabase
        .from("demand_signals")
        .select("*")
        .order("polled_date", { ascending: false })
        .limit(50),
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(300),
    ]);
    if (tp.error || ds.error) dbError = true;
    topics = (tp.data as TopicPerformanceRow[]) ?? [];
    demand = (ds.data as DemandSignalRow[]) ?? [];
    signals = (fs.data as FeedbackSignalRow[]) ?? [];
  }

  // Group feedback signals by topic for the "Why?" explanation (real data).
  const signalsByTopic = new Map<string, FeedbackSignalRow[]>();
  for (const s of signals) {
    if (!s.topic) continue;
    const arr = signalsByTopic.get(s.topic);
    if (arr) arr.push(s);
    else signalsByTopic.set(s.topic, [s]);
  }

  const scored = topics.length;
  const strong = topics.filter((tp) => tp.score >= 50).length;
  const topScore = topics.length > 0 ? topics[0].score : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">{t.topics.title}</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">{t.topics.subtitle}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard label={t.topics.scored} value={<AnimatedNumber value={scored} />} sub={t.topics.scoredSub} />
        <StatCard
          label={t.topics.strong}
          value={<AnimatedNumber value={strong} />}
          tone="ok"
          sub={t.topics.strongSub}
        />
        <StatCard
          label={t.topics.topScore}
          value={topScore === null ? t.common.na : topScore.toFixed(0)}
          tone={topScore !== null && topScore >= 50 ? "ok" : "warn"}
          sub={t.topics.topScoreSub}
        />
      </div>

      <Panel title={t.topics.scores}>
        {dbError ? (
          <EmptyState>{t.topics.readErr}</EmptyState>
        ) : topics.length === 0 ? (
          <EmptyState>{t.topics.empty}</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="px-4 py-2 font-semibold">{t.topics.thTopic}</th>
                  <th className="px-4 py-2 text-right font-semibold">{t.topics.thScore}</th>
                  <th className="px-4 py-2 text-right font-semibold">{t.topics.thVideos}</th>
                  <th className="px-4 py-2 text-right font-semibold">{t.topics.thAvgViews}</th>
                  <th className="px-4 py-2 font-semibold">{t.topics.thReason}</th>
                  <th className="px-4 py-2 font-semibold">{t.topics.thUpdated}</th>
                </tr>
              </thead>
              <tbody>
                {topics.map((tp) => (
                  <tr key={tp.topic} className="border-b border-[var(--color-border)]/50 transition-colors hover:bg-[var(--color-panel-2)]">
                    <td className="px-4 py-2 text-[var(--color-fg)]">{tp.topic}</td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <ExplainScore score={tp.score} reason={tp.reason} signals={signalsByTopic.get(tp.topic) ?? []} />
                        <span
                          className="mono font-bold tabular-nums"
                          style={{ color: tp.score >= 50 ? "var(--color-ok)" : "var(--color-warn)" }}
                        >
                          {tp.score.toFixed(0)}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                      {num(tp.videos_analyzed)}
                    </td>
                    <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                      {decimal(tp.avg_views_per_day)}
                    </td>
                    <td className="px-4 py-2 max-w-xs truncate text-[var(--color-muted)]">
                      {tp.reason ?? t.common.na}
                    </td>
                    <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">
                      {relativeTime(tp.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title={t.topics.demand}>
        {demand.length === 0 ? (
          <EmptyState>{t.topics.noDemand}</EmptyState>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {demand.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-[var(--color-panel-2)]"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-[var(--color-fg)]">{d.topic_phrase}</div>
                  <div className="mono text-[10px] text-[var(--color-muted)]">
                    {fmt(t.topics.polled, { t: relativeTime(d.polled_date) })}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="mono text-lg font-bold tabular-nums text-[var(--color-primary)]">
                    {num(d.mention_count)}
                  </div>
                  <div className="mono text-[9px] uppercase tracking-widest text-[var(--color-muted)]">
                    {t.topics.mentions}
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
