import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, StatusPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";
import type { SystemEventRow } from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const RECENT_MS = 3 * 24 * 60 * 60 * 1000; // "recent" = last 3 days

interface Health {
  name: string;
  detail: string;
  tone: "ok" | "warn" | "fail" | "idle";
  status: string;
  lastSuccess: string | null;
}

/** Latest ts among events whose `event` matches any of `names`, optionally only failures. */
function latest(events: SystemEventRow[], names: string[], failedOnly = false): string | null {
  const hit = events.find(
    (e) => names.some((n) => e.event === n) && (!failedOnly || (e.status ?? "").toLowerCase() === "failed"),
  );
  return hit?.ts ?? null;
}

function derive(name: string, ok: string[], fail: string[], events: SystemEventRow[]): Health {
  const lastOk = latest(events, ok);
  const lastFail = latest(events, fail, true);
  const recent = lastOk && Date.now() - new Date(lastOk).getTime() < RECENT_MS;
  if (recent) return { name, detail: "recent successful activity", tone: "ok", status: "HEALTHY", lastSuccess: lastOk };
  if (lastFail) return { name, detail: "recent failures, no success", tone: "warn", status: "DEGRADED", lastSuccess: lastOk };
  if (lastOk) return { name, detail: "last activity is stale", tone: "idle", status: "UNKNOWN", lastSuccess: lastOk };
  return { name, detail: "no activity in the event stream", tone: "idle", status: "UNKNOWN", lastSuccess: null };
}

export default async function IntegrationsPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let dbOk = false;
  if (supabase) {
    const { data, error } = await supabase
      .from("system_events")
      .select("*")
      .order("ts", { ascending: false })
      .limit(1000);
    dbOk = !error;
    events = (data as SystemEventRow[]) ?? [];
  }

  const items: Health[] = [
    {
      name: "Supabase / Database",
      detail: dbOk ? "query succeeded this request" : "query failed",
      tone: dbOk ? "ok" : "fail",
      status: dbOk ? "HEALTHY" : "OFFLINE",
      lastSuccess: dbOk ? new Date().toISOString() : null,
    },
    derive("YouTube", ["upload.completed", "video.published"], ["upload.failed"], events),
    derive("Gemini (script/topic)", ["script.completed", "topic.selected"], ["agent.failed"], events),
    derive("Intelligence poll", ["system.heartbeat"], [], events),
    derive("Feedback loop", ["feedback.generated", "feedback.applied"], [], events),
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">Integration Health</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">
          Derived from the real event stream — the bot has no live health-check endpoint, so no recent events means
          UNKNOWN, not necessarily down. No response times are invented.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((h) => (
          <div key={h.name} className="panel p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-[var(--color-fg)]">{h.name}</span>
              <StatusPill tone={h.tone} label={h.status} />
            </div>
            <p className="mt-1.5 mono text-[11px] text-[var(--color-muted)]">{h.detail}</p>
            <p className="mt-0.5 mono text-[11px] text-[var(--color-muted)]">
              last success: {h.lastSuccess ? relativeTime(h.lastSuccess) : "N/A"}
            </p>
          </div>
        ))}
      </div>

      <Panel title="How this is measured">
        <div className="p-4 text-[11px] leading-relaxed text-[var(--color-muted)]">
          Each integration&apos;s status comes from the presence and recency of its own events in{" "}
          <code className="mono text-[var(--color-primary)]">system_events</code>: e.g. YouTube is HEALTHY when an{" "}
          <code className="mono">upload.completed</code> / <code className="mono">video.published</code> event landed in
          the last 3 days, DEGRADED on recent failures, UNKNOWN when the stream is silent. This is honest by
          construction — it reports what actually happened, never a fabricated ping.
        </div>
      </Panel>
    </div>
  );
}
