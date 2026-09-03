import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, EmptyState, StatCard } from "@/components/ui";
import { statusTone } from "@/lib/format";
import type { SystemEventRow } from "@/lib/types";
import { AgentCard, type AgentSummary } from "@/components/agents/AgentCard";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function deriveAgents(events: SystemEventRow[]): AgentSummary[] {
  // Events arrive newest-first. Bucket them per agent, preserving that order.
  const byAgent = new Map<string, SystemEventRow[]>();
  for (const e of events) {
    if (!e.agent) continue;
    const list = byAgent.get(e.agent);
    if (list) list.push(e);
    else byAgent.set(e.agent, [e]);
  }

  const summaries: AgentSummary[] = [];
  for (const [agent, rows] of byAgent) {
    const latest = rows[0];
    const tone = statusTone(latest.status);
    const status: AgentSummary["status"] =
      tone === "run" ? "RUNNING" : tone === "fail" ? "FAILED" : "IDLE";
    // A completed newest event = healthy-but-idle (green); a truly unknown
    // status stays grey idle.
    const displayTone: AgentSummary["tone"] =
      tone === "run" ? "run" : tone === "fail" ? "fail" : tone === "ok" ? "ok" : "idle";

    const lastSuccess = rows.find((r) => statusTone(r.status) === "ok")?.ts ?? null;
    const lastFailure = rows.find((r) => statusTone(r.status) === "fail")?.ts ?? null;

    summaries.push({
      agent,
      status,
      tone: displayTone,
      currentTask: latest.event,
      lastActivity: latest.ts,
      lastSuccess,
      lastFailure,
      durationMs: latest.duration_ms,
      eventCount: rows.length,
    });
  }

  // Running first, then failed, then the rest by most recent activity.
  const rank = { RUNNING: 0, FAILED: 1, IDLE: 2 } as const;
  return summaries.sort((a, b) => {
    if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status];
    return new Date(b.lastActivity ?? 0).getTime() - new Date(a.lastActivity ?? 0).getTime();
  });
}

export default async function AgentsPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let dbError = false;

  if (supabase) {
    const ev = await supabase
      .from("system_events")
      .select("*")
      .order("ts", { ascending: false })
      .limit(500);
    if (ev.error) dbError = true;
    events = (ev.data as SystemEventRow[]) ?? [];
  }

  const agents = deriveAgents(events);
  const running = agents.filter((a) => a.status === "RUNNING").length;
  const failed = agents.filter((a) => a.status === "FAILED").length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Agents</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Derived from the live system_events stream — no separate agents table
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Agents seen" value={agents.length} sub="distinct, recent window" />
        <StatCard label="Running" value={running} tone={running ? "run" : "idle"} sub={running ? "active now" : "none active"} />
        <StatCard label="Failed" value={failed} tone={failed ? "fail" : "ok"} sub={failed ? "latest event failed" : "none failing"} />
        <StatCard label="Events scanned" value={events.length} sub="most recent 500" />
      </div>

      <Panel title="Agent Roster">
        {dbError ? (
          <EmptyState>Could not reach the database. The agent roster is unavailable right now.</EmptyState>
        ) : agents.length === 0 ? (
          <EmptyState>No agent activity yet. Once the pipeline runs, each agent appears here with its latest state.</EmptyState>
        ) : (
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((a) => (
              <AgentCard key={a.agent} agent={a} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
