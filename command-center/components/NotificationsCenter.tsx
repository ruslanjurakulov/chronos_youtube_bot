"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { buildNotifications, type Notification, type NotificationKind } from "@/lib/intelligence";
import { relativeTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/context";
import type { Dictionary } from "@/lib/i18n";
import type { FeedbackSignalRow, SystemEventRow } from "@/lib/types";

const SEEN_KEY = "chronos_notif_seen";
const CLEARED_KEY = "chronos_notif_cleared";

const KIND_LABEL: Record<NotificationKind, keyof Dictionary["ops"]> = {
  published: "notifPublished",
  error: "notifError",
  learning: "notifLearning",
  anomaly: "notifAnomaly",
};
const KIND_COLOR: Record<NotificationKind, string> = {
  published: "var(--color-primary)",
  error: "var(--color-fail)",
  learning: "var(--color-ok)",
  anomaly: "var(--color-warn)",
};

/**
 * Header notifications derived from real rows only — published videos,
 * failures, and HIGH_/LOW_ learning signals. Live via Realtime; unread is
 * tracked against a per-device "last seen" timestamp, and Clear hides
 * everything up to now (also per-device). Nothing is fabricated.
 */
export function NotificationsCenter() {
  const { t } = useI18n();
  const [events, setEvents] = useState<SystemEventRow[]>([]);
  const [signals, setSignals] = useState<FeedbackSignalRow[]>([]);
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState<number>(0);
  const [cleared, setCleared] = useState<number>(0);
  const ref = useRef<HTMLDivElement>(null);
  const knownKeys = useRef<Set<string>>(new Set());

  useEffect(() => {
    try {
      setSeen(Number(localStorage.getItem(SEEN_KEY) ?? 0));
      setCleared(Number(localStorage.getItem(CLEARED_KEY) ?? 0));
    } catch {
      // ignore
    }
    const supabase = createClient();
    if (!supabase) return;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    (async () => {
      const [ev, sg] = await Promise.all([
        supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(100),
        supabase.from("feedback_signals").select("*").order("analyzed_date", { ascending: false }).limit(100),
      ]);
      const rows = (ev.data as SystemEventRow[]) ?? [];
      rows.forEach((r) => knownKeys.current.add(r.event_key));
      setEvents(rows);
      setSignals((sg.data as FeedbackSignalRow[]) ?? []);

      channel = supabase
        .channel("chronos_notifications")
        .on("postgres_changes", { event: "INSERT", schema: "public", table: "system_events" }, (payload) => {
          const row = payload.new as SystemEventRow;
          if (knownKeys.current.has(row.event_key)) return;
          knownKeys.current.add(row.event_key);
          setEvents((prev) => [row, ...prev].slice(0, 200));
        })
        .subscribe();
    })();

    return () => {
      if (channel) supabase.removeChannel(channel);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const notifications = useMemo(
    () => buildNotifications(events, signals, 30).filter((n) => new Date(n.ts).getTime() > cleared),
    [events, signals, cleared],
  );
  const unread = useMemo(() => notifications.filter((n) => new Date(n.ts).getTime() > seen).length, [notifications, seen]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      const now = Date.now();
      setSeen(now);
      try {
        localStorage.setItem(SEEN_KEY, String(now));
      } catch {
        // ignore
      }
    }
  }

  function clearAll() {
    const now = Date.now();
    setCleared(now);
    try {
      localStorage.setItem(CLEARED_KEY, String(now));
    } catch {
      // ignore
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={toggle}
        aria-label={t.ops.notifTitle}
        className="press relative grid size-8 place-items-center rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:border-[var(--color-primary-dim)]"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span
            className="absolute -right-1 -top-1 grid min-w-[16px] place-items-center rounded-full px-1 text-[9px] font-bold text-[var(--color-on-accent)]"
            style={{ background: "var(--color-primary)" }}
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="reveal absolute right-0 z-50 mt-1.5 w-80 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] shadow-[var(--shadow-elevated)]">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
            <span className="mono text-[10px] font-bold uppercase tracking-widest text-[var(--color-fg)]">{t.ops.notifTitle}</span>
            {notifications.length > 0 && (
              <button type="button" onClick={clearAll} className="press mono text-[10px] text-[var(--color-muted)] hover:text-[var(--color-fg)]">
                {t.ops.notifClear}
              </button>
            )}
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {notifications.length === 0 ? (
              <li className="p-4 text-center mono text-xs text-[var(--color-muted)]">{t.ops.notifEmpty}</li>
            ) : (
              notifications.map((n: Notification) => (
                <li key={n.id} className="flex items-start gap-2.5 border-b border-[var(--color-border)]/60 px-3 py-2 last:border-0">
                  <span className="mt-1 size-1.5 shrink-0 rounded-full" style={{ background: KIND_COLOR[n.kind] }} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[12px] text-[var(--color-fg)]">{String(t.ops[KIND_LABEL[n.kind]])}</div>
                    <div className="mono truncate text-[10px] text-[var(--color-muted)]">{n.subject}</div>
                  </div>
                  <span className="mono shrink-0 text-[9px] text-[var(--color-muted)]">{relativeTime(n.ts)}</span>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
