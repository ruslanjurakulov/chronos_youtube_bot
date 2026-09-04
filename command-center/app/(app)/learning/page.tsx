import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { LearningView } from "@/components/intel/LearningView";
import { toDecisionSignal, type DecisionSignal } from "@/lib/decisions";
import { deriveTopicIntel } from "@/lib/memory";
import { getDictionary } from "@/lib/i18n/server";
import type { FeedbackSignalRow, TopicPerformanceRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function LearningPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let signals: FeedbackSignalRow[] = [];
  let topicPerf: TopicPerformanceRow[] = [];
  let videos: VideoRow[] = [];

  if (supabase) {
    const [fs, tp, vid] = await Promise.all([
      supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(300),
      supabase.from("topic_performance").select("*").order("score", { ascending: false }),
      supabase.from("videos").select("*").order("published_at", { ascending: false }).limit(200),
    ]);
    signals = (fs.data as FeedbackSignalRow[]) ?? [];
    topicPerf = (tp.data as TopicPerformanceRow[]) ?? [];
    videos = (vid.data as VideoRow[]) ?? [];
  }

  const decisionSignals = signals
    .map(toDecisionSignal)
    .filter((s): s is DecisionSignal => s !== null);
  const topics = deriveTopicIntel(topicPerf, signals, videos);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">{t.intel.learningTitle}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.intel.learningSubtitle}</p>
      </div>
      <LearningView signals={decisionSignals} topics={topics} />
    </div>
  );
}
