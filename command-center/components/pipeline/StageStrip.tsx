"use client";

import { timeOfDay } from "@/lib/format";
import { useI18n } from "@/lib/i18n/context";

export type StageState = "WAITING" | "COMPLETED" | "RUNNING" | "FAILED";

export interface StageView {
  key: string;
  label: string;
  state: StageState;
  ts: string | null;
}

const STATE_COLOR: Record<StageState, string> = {
  WAITING: "var(--color-idle)",
  COMPLETED: "var(--color-ok)",
  RUNNING: "var(--color-primary)",
  FAILED: "var(--color-fail)",
};

/** One stage node + the connector line into the next stage. */
function StageNode({ stage, last }: { stage: StageView; last: boolean }) {
  const color = STATE_COLOR[stage.state];
  const filled = stage.state !== "WAITING";
  return (
    <li className="flex min-w-0 flex-1 items-start">
      <div className="flex min-w-0 flex-col items-center gap-1">
        <span
          className={stage.state === "RUNNING" ? "glow-dot live-ring" : undefined}
          style={{
            width: 14,
            height: 14,
            borderRadius: 999,
            background: filled ? color : "transparent",
            border: `2px solid ${color}`,
            color,
            flexShrink: 0,
            transition: "background 0.3s ease, border-color 0.3s ease",
          }}
        />
        <span className="mono text-center text-[10px] leading-tight" style={{ color: filled ? "var(--color-fg)" : "var(--color-muted)" }}>
          {stage.label}
        </span>
        <span className="mono text-center text-[9px] text-[var(--color-muted)]">
          {stage.ts ? timeOfDay(stage.ts) : "—"}
        </span>
      </div>
      {!last && (
        <span
          aria-hidden
          className="mt-[6px] h-[2px] flex-1"
          style={{ background: filled ? color : "var(--color-border)", opacity: filled ? 0.6 : 1 }}
        />
      )}
    </li>
  );
}

export function StageStrip({ stages }: { stages: StageView[] }) {
  return (
    <ol className="flex items-start gap-1">
      {stages.map((s, i) => (
        <StageNode key={s.key} stage={s} last={i === stages.length - 1} />
      ))}
    </ol>
  );
}

export function StageLegend() {
  const { t } = useI18n();
  const items: { state: StageState; label: string }[] = [
    { state: "WAITING", label: t.pipeline.legendWaiting },
    { state: "RUNNING", label: t.pipeline.legendRunning },
    { state: "COMPLETED", label: t.pipeline.legendCompleted },
    { state: "FAILED", label: t.pipeline.legendFailed },
  ];
  return (
    <div className="flex flex-wrap items-center gap-4">
      {items.map((it) => (
        <span key={it.state} className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] text-[var(--color-muted)]">
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: 999,
              background: it.state === "WAITING" ? "transparent" : STATE_COLOR[it.state],
              border: `2px solid ${STATE_COLOR[it.state]}`,
            }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}
