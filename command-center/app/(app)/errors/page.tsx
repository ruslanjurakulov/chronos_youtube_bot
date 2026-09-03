import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { StatCard, Panel, EmptyState } from "@/components/ui";
import { statusTone } from "@/lib/format";
import type { SystemEventRow } from "@/lib/types";
import { ErrorTable } from "@/components/errors/ErrorTable";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const DAY_MS = 24 * 60 * 60 * 1000;
const FETCH_LIMIT = 300;

/** A failure is anything whose status tone is "fail", or whose event name ends
 *  in `.failed` (upload.failed, agent.failed, job.failed, …). */
function isFailure(e: SystemEventRow): boolean {
  return statusTone(e.status) === "fail" || e.event.endsWith(".failed");
}

export default async function ErrorCenter() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let queryFailed = false;

  if (supabase) {
    const { data, error } = await supabase
      .from("system_events")
      .select("*")
      .order("ts", { ascending: false })
      .limit(FETCH_LIMIT);
    if (error) queryFailed = true;
    events = (data as SystemEventRow[]) ?? [];
  }

  const errors = events.filter(isFailure);
  const errors24h = errors.filter(
    (e) => Date.now() - new Date(e.ts).getTime() < DAY_MS,
  ).length;
  const lastError = errors[0]?.ts ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Error Center</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Failures derived from the system_events stream — real events only
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Errors (24h)"
          value={errors24h}
          tone={errors24h ? "fail" : "ok"}
          sub={errors24h ? "needs attention" : "none"}
        />
        <StatCard
          label="Errors (shown)"
          value={errors.length}
          tone={errors.length ? "warn" : "ok"}
          sub={`of ${events.length} recent events`}
        />
        <StatCard
          label="Scanned"
          value={events.length}
          sub={`most recent ${FETCH_LIMIT}`}
        />
        <StatCard
          label="Last error"
          value={lastError ? "SEEN" : "NONE"}
          tone={lastError ? "warn" : "ok"}
          sub={lastError ? "see table below" : "clean window"}
        />
      </div>

      <Panel title="Failure Events">
        {queryFailed ? (
          <EmptyState>
            Could not read system_events — the database query failed. No data shown.
          </EmptyState>
        ) : (
          <ErrorTable rows={errors} />
        )}
      </Panel>
    </div>
  );
}
