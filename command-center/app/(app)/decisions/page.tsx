import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, EmptyState } from "@/components/ui";
import { DecisionList } from "@/components/intel/DecisionList";
import { deriveDecisions, scoreLineage, type LineageRow } from "@/lib/decisions";
import { getDictionary } from "@/lib/i18n/server";
import type { FeedbackSignalRow, SystemEventRow, TopicPerformanceRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function DecisionsPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let topicPerf: TopicPerformanceRow[] = [];
  let signals: FeedbackSignalRow[] = [];

  if (supabase) {
    const [ev, tp, fs] = await Promise.all([
      supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(500),
      supabase.from("topic_performance").select("*").order("score", { ascending: false }),
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(300),
    ]);
    events = (ev.data as SystemEventRow[]) ?? [];
    topicPerf = (tp.data as TopicPerformanceRow[]) ?? [];
    signals = (fs.data as FeedbackSignalRow[]) ?? [];
  }

  const decisions = deriveDecisions(events, topicPerf, signals);

  // Lineage per topic — where each score actually came from.
  const signalCountByTopic = new Map<string, number>();
  for (const s of signals) {
    if (!s.topic) continue;
    signalCountByTopic.set(s.topic, (signalCountByTopic.get(s.topic) ?? 0) + 1);
  }
  const lineage: Record<string, LineageRow[]> = {};
  for (const p of topicPerf) {
    lineage[p.topic] = scoreLineage(p, signalCountByTopic.get(p.topic) ?? 0);
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">{t.intel.decisionsTitle}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.intel.decisionsSubtitle}</p>
      </div>

      <Panel title={t.intel.decisionsTitle}>
        {decisions.length === 0 ? (
          <EmptyState>{t.intel.noDecisions}</EmptyState>
        ) : (
          <DecisionList decisions={decisions} lineage={lineage} />
        )}
      </Panel>
    </div>
  );
}
