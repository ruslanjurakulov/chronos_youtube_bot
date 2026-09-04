import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { IntelligenceMap } from "@/components/intelligence/IntelligenceMap";
import { ChronosCore } from "@/components/ChronosCore";
import { getDictionary } from "@/lib/i18n/server";
import type { SystemEventRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function IntelligencePage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  if (supabase) {
    const { data } = await supabase
      .from("system_events")
      .select("*")
      .order("ts", { ascending: false })
      .limit(500);
    events = (data as SystemEventRow[]) ?? [];
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">{t.ops.intelTitle}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.ops.intelSubtitle}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel flex items-center justify-center p-5">
          <ChronosCore initial={events} size={200} />
        </div>
        <div className="lg:col-span-2">
          <IntelligenceMap initial={events} />
        </div>
      </div>
    </div>
  );
}
