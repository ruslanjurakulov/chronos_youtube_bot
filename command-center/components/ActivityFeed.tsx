"use client";

import { useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { statusTone, timeOfDay } from "@/lib/format";
import type { SystemEventRow } from "@/lib/types";
import { StatusPill } from "@/components/ui";
import { useI18n } from "@/lib/i18n/context";

const TONE_COLOR: Record<string, string> = {
  ok: "var(--color-ok)",
  run: "var(--color-primary)",
  fail: "var(--color-fail)",
  idle: "var(--color-idle)",
};

/**
 * Live activity feed. Seeded with server-fetched events, then subscribes to
 * Supabase Realtime so new `system_events` inserts appear without a refresh —
 * real events from the backend, never synthetic timers. Rows that arrive over
 * the subscription get a subtle entrance animation; the seed rows do not.
 */
export function ActivityFeed({ initial }: { initial: SystemEventRow[] }) {
  const { t, fmt } = useI18n();
  const [events, setEvents] = useState<SystemEventRow[]>(initial);
  const [live, setLive] = useState(false);
  const seen = useRef(new Set(initial.map((e) => e.event_key)));
  // Keys that arrived via realtime (post-mount) — these animate in.
  const [fresh, setFresh] = useState<Set<string>>(new Set());

  useEffect(() => {
    const supabase = createClient();
    if (!supabase) return;
    const channel = supabase
      .channel("system_events_feed")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "system_events" },
        (payload) => {
          const row = payload.new as SystemEventRow;
          if (seen.current.has(row.event_key)) return;
          seen.current.add(row.event_key);
          setEvents((prev) => [row, ...prev].slice(0, 100));
          setFresh((prev) => new Set(prev).add(row.event_key));
        },
      )
      .subscribe((status) => setLive(status === "SUBSCRIBED"));

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2">
        <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
          {fmt(t.feed.events, { n: events.length })}
        </span>
        <StatusPill tone={live ? "run" : "idle"} label={live ? t.status.live : t.status.polled} live={live} />
      </div>
      <ol className="min-h-0 flex-1 divide-y divide-[var(--color-border)] overflow-y-auto">
        {events.length === 0 && (
          <li className="p-6 text-center mono text-xs text-[var(--color-muted)]">
            {t.feed.noEvents}
          </li>
        )}
        {events.map((e) => {
          const tone = statusTone(e.status);
          return (
            <li
              key={e.event_key}
              className={`flex items-center gap-3 px-4 py-2 text-sm${fresh.has(e.event_key) ? " row-enter" : ""}`}
            >
              <span className="mono w-16 shrink-0 text-[10px] text-[var(--color-muted)]">
                {timeOfDay(e.ts)}
              </span>
              <span
                className="glow-dot size-1.5 shrink-0 rounded-full"
                style={{ color: TONE_COLOR[tone], background: TONE_COLOR[tone] }}
              />
              <span className="mono shrink-0 text-[11px] text-[var(--color-primary)]">
                {e.agent ?? t.common.system}
              </span>
              <span className="truncate text-[var(--color-fg)]">{e.event}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
