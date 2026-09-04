"use client";

import { useMemo } from "react";
import { useRealtimeEvents } from "@/lib/useRealtimeEvents";
import { deriveCoreState, type CoreState } from "@/lib/intelligence";
import { relativeTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/context";
import { fmt } from "@/lib/i18n";
import type { SystemEventRow } from "@/lib/types";
import type { Dictionary } from "@/lib/i18n";

const ACTIVE: CoreState[] = ["observing", "analyzing", "learning", "deciding", "generating", "publishing", "measuring"];

const STATE_LABEL: Record<CoreState, keyof Dictionary["ops"]> = {
  idle: "stateIdle",
  observing: "stateObserving",
  analyzing: "stateAnalyzing",
  learning: "stateLearning",
  deciding: "stateDeciding",
  generating: "stateGenerating",
  publishing: "statePublishing",
  measuring: "stateMeasuring",
  error: "stateError",
  disconnected: "stateDisconnected",
};

/** Map the live core state onto the OBSERVE→…→IMPROVE cycle phase to highlight. */
const CYCLE: { key: keyof Dictionary["ops"]; states: CoreState[] }[] = [
  { key: "cycleObserve", states: ["observing"] },
  { key: "cycleAnalyze", states: ["analyzing"] },
  { key: "cycleLearn", states: ["learning"] },
  { key: "cycleDecide", states: ["deciding"] },
  { key: "cycleCreate", states: ["generating"] },
  { key: "cyclePublish", states: ["publishing"] },
  { key: "cycleMeasure", states: ["measuring"] },
];

/**
 * The Chronos Core — a holographic energy orb reflecting the *real* system
 * state derived from the newest event and the realtime connection. Calm when
 * idle (the honest resting state between polls), animated only when real
 * activity is arriving; red on a real failure; dimmed when disconnected.
 */
export function ChronosCore({
  initial,
  size = 200,
  showCycle = true,
}: {
  initial: SystemEventRow[];
  size?: number;
  showCycle?: boolean;
}) {
  const { t } = useI18n();
  const { events, connected } = useRealtimeEvents(initial, "chronos_core");
  // Optimistic before the first subscribe callback so we don't flash "disconnected".
  const state = useMemo(() => deriveCoreState(events, connected ?? true), [events, connected]);

  const isActive = ACTIVE.includes(state);
  const accent =
    state === "error" ? "var(--color-fail)" : state === "disconnected" ? "var(--color-idle)" : "var(--color-primary)";
  const accent2 = state === "error" || state === "disconnected" ? accent : "var(--color-secondary)";
  const glow = state === "disconnected" ? 0.14 : state === "error" ? 0.5 : isActive ? 0.6 : 0.32;
  const paused = state === "disconnected";
  const lastTs = events[0]?.ts ?? null;

  const C = size / 2;
  const ringOuter = C - 6;
  const ringMid = C - 22;
  const coreR = C - 46;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        {/* soft glow */}
        <div
          className={paused ? undefined : "core-flare"}
          style={{
            position: "absolute",
            inset: "8%",
            borderRadius: "50%",
            background: `radial-gradient(circle, ${accent} 0%, transparent 68%)`,
            opacity: glow,
            filter: "blur(14px)",
          }}
        />
        <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={String(t.ops[STATE_LABEL[state]])}>
          <defs>
            <radialGradient id="coreGrad" cx="42%" cy="38%" r="70%">
              <stop offset="0%" stopColor={accent2} stopOpacity="0.95" />
              <stop offset="60%" stopColor={accent} stopOpacity="0.85" />
              <stop offset="100%" stopColor={accent} stopOpacity="0.35" />
            </radialGradient>
          </defs>

          {/* outer ring — slow, dashed arc */}
          <g className={paused ? undefined : "core-spin"} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
            <circle cx={C} cy={C} r={ringOuter} fill="none" stroke={accent} strokeOpacity="0.25" strokeWidth="1" />
            <circle
              cx={C}
              cy={C}
              r={ringOuter}
              fill="none"
              stroke={accent}
              strokeOpacity="0.8"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={`${ringOuter * 0.5} ${ringOuter * 4}`}
            />
            <circle cx={C + ringOuter} cy={C} r="2.5" fill={accent} />
          </g>

          {/* mid ring — counter-rotating, faster when active */}
          <g className={paused ? undefined : isActive ? "core-spin-fast" : "core-spin-rev"} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
            <circle cx={C} cy={C} r={ringMid} fill="none" stroke={accent2} strokeOpacity="0.35" strokeWidth="1" strokeDasharray="2 8" />
            <circle cx={C} cy={C - ringMid} r="2" fill={accent2} />
          </g>

          {/* core */}
          <g className={paused ? undefined : "core-breathe"} style={{ transformBox: "fill-box", transformOrigin: "center" }}>
            <circle cx={C} cy={C} r={coreR} fill="url(#coreGrad)" />
            <circle cx={C} cy={C} r={coreR} fill="none" stroke={accent} strokeOpacity="0.5" strokeWidth="1" />
          </g>
        </svg>
      </div>

      <div className="text-center">
        <div className="mono text-[10px] uppercase tracking-[0.25em] text-[var(--color-muted)]">{t.ops.coreTitle}</div>
        <div className="font-display text-base font-semibold" style={{ color: accent }}>
          {String(t.ops[STATE_LABEL[state]])}
        </div>
        <div className="mono text-[10px] text-[var(--color-muted)]">
          {lastTs ? fmt(t.ops.coreLastEvent, { t: relativeTime(lastTs) }) : t.ops.coreNoEvents}
        </div>
      </div>

      {showCycle && (
        <div className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1">
          {CYCLE.map((c, i) => {
            const on = c.states.includes(state);
            return (
              <span key={c.key} className="flex items-center gap-1.5">
                <span
                  className="mono text-[9px] uppercase tracking-widest transition-colors"
                  style={{ color: on ? "var(--color-primary)" : "var(--color-idle)", opacity: on ? 1 : 0.6 }}
                >
                  {String(t.ops[c.key])}
                </span>
                {i < CYCLE.length - 1 && <span className="text-[8px] text-[var(--color-idle)]">›</span>}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
