import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { AdvisoryPanel } from "@/components/intelligence/AdvisoryPanel";
import { getDictionary } from "@/lib/i18n/server";
import { getChannelSelection } from "@/lib/channels-server";
import { scopeQuery } from "@/lib/channels";
import type { SystemEventRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AdvisoryIntelligencePage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();
  const selection = await getChannelSelection();

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  if (supabase) {
    const { data } = await scopeQuery(
        supabase.from("system_events").select("*"),
        selection, { nullIsGlobal: true },
      )
      .order("ts", { ascending: false })
      .limit(500);
    events = (data as SystemEventRow[]) ?? [];
  }

  return (
    <div className="rhythm stagger-enter">
      <div>
        <h1 className="t-hero">{t.ops.advTitle}</h1>
        <p className="t-lead mt-4">{t.ops.advSubtitle}</p>
      </div>

      <AdvisoryPanel initial={events} selection={selection} />
    </div>
  );
}
