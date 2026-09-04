import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { MemoryView } from "@/components/intel/MemoryView";
import { deriveMemories, deriveOpportunities } from "@/lib/memory";
import { getDictionary } from "@/lib/i18n/server";
import type { DemandSignalRow, FeedbackSignalRow, TopicPerformanceRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function MemoryPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let topicPerf: TopicPerformanceRow[] = [];
  let signals: FeedbackSignalRow[] = [];
  let demand: DemandSignalRow[] = [];

  if (supabase) {
    const [tp, fs, ds] = await Promise.all([
      supabase.from("topic_performance").select("*").order("score", { ascending: false }),
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(300),
      supabase.from("demand_signals").select("*").order("polled_date", { ascending: false }).limit(100),
    ]);
    topicPerf = (tp.data as TopicPerformanceRow[]) ?? [];
    signals = (fs.data as FeedbackSignalRow[]) ?? [];
    demand = (ds.data as DemandSignalRow[]) ?? [];
  }

  const memories = deriveMemories(topicPerf, signals);
  const opportunities = deriveOpportunities(topicPerf, demand);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">{t.intel.memoryTitle}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.intel.memorySubtitle}</p>
      </div>
      <MemoryView memories={memories} opportunities={opportunities} />
    </div>
  );
}
