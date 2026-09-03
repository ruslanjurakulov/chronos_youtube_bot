import { StatusPill } from "@/components/ui";
import { relativeTime } from "@/lib/format";

export interface AgentSummary {
  agent: string;
  /** Display status derived from the newest event's statusTone. */
  status: "RUNNING" | "IDLE" | "FAILED";
  tone: "run" | "ok" | "fail" | "idle";
  currentTask: string;
  lastActivity: string | null;
  lastSuccess: string | null;
  lastFailure: string | null;
  durationMs: number | null;
  eventCount: number;
}

function durationLabel(ms: number | null): string {
  if (ms === null || ms === undefined) return "N/A";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * One agent's derived state. All fields come from the `system_events` stream —
 * there is no agents table, so status/task/timestamps are read off the agent's
 * most recent events. Missing signals render N/A rather than being invented.
 */
export function AgentCard({ agent }: { agent: AgentSummary }) {
  const accent =
    agent.tone === "run"
      ? "var(--color-primary)"
      : agent.tone === "fail"
        ? "var(--color-fail)"
        : agent.tone === "ok"
          ? "var(--color-ok)"
          : "var(--color-idle)";

  return (
    <div className="panel flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="mono truncate text-sm font-bold text-[var(--color-primary)]">
            {agent.agent}
          </div>
          <div className="mono mt-0.5 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
            {agent.eventCount} recent events
          </div>
        </div>
        <StatusPill tone={agent.tone} label={agent.status} />
      </div>

      <div className="rounded-md border-l-2 px-3 py-2" style={{ borderColor: accent, background: "var(--color-panel-2)" }}>
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
          Current task
        </div>
        <div className="mono mt-0.5 truncate text-sm text-[var(--color-fg)]">{agent.currentTask}</div>
        <div className="mono mt-0.5 text-[11px] text-[var(--color-muted)]">
          {agent.durationMs !== null ? `took ${durationLabel(agent.durationMs)} · ` : ""}
          {agent.lastActivity ? relativeTime(agent.lastActivity) : "N/A"}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2">
        <div>
          <dt className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
            Last success
          </dt>
          <dd className="mono mt-0.5 text-[11px]" style={{ color: agent.lastSuccess ? "var(--color-ok)" : "var(--color-muted)" }}>
            {agent.lastSuccess ? relativeTime(agent.lastSuccess) : "N/A"}
          </dd>
        </div>
        <div>
          <dt className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
            Last failure
          </dt>
          <dd className="mono mt-0.5 text-[11px]" style={{ color: agent.lastFailure ? "var(--color-fail)" : "var(--color-muted)" }}>
            {agent.lastFailure ? relativeTime(agent.lastFailure) : "N/A"}
          </dd>
        </div>
      </dl>
    </div>
  );
}
