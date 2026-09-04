import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { AutonomyView } from "@/components/autonomy/AutonomyView";
import {
  autonomousActions,
  autonomyHealth,
  autonomyPosture,
  duplicateTopics,
  failureLearning,
  publishingWindow,
} from "@/lib/autonomy";
import { getDictionary } from "@/lib/i18n/server";
import type { MetricsSnapshotRow, SystemEventRow, VideoRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AutonomyPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let videos: VideoRow[] = [];
  let snapshots: MetricsSnapshotRow[] = [];

  if (supabase) {
    const [ev, vid, snap] = await Promise.all([
      supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(500),
      supabase.from("videos").select("*").order("published_at", { ascending: false }).limit(500),
      supabase.from("metrics_snapshots").select("*").order("snapshot_date", { ascending: false }).limit(2000),
    ]);
    events = (ev.data as SystemEventRow[]) ?? [];
    videos = (vid.data as VideoRow[]) ?? [];
    snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">{t.auto.title}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.auto.subtitle}</p>
      </div>
      <AutonomyView
        posture={autonomyPosture(events)}
        health={autonomyHealth(events)}
        actions={autonomousActions(events, 100)}
        failures={failureLearning(events)}
        window={publishingWindow(videos, snapshots)}
        duplicates={duplicateTopics(videos)}
      />
    </div>
  );
}
