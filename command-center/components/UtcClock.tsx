"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n/context";

/** A subtle live UTC clock — a real system micro-detail, updated each second. */
export function UtcClock() {
  const { t } = useI18n();
  const [now, setNow] = useState<string | null>(null);

  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "UTC",
          hour12: false,
        }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  // Render nothing until mounted so server/client first paint match.
  if (!now) return null;
  return (
    <span className="mono hidden items-center gap-1.5 text-[11px] text-[var(--color-muted)] lg:inline-flex" aria-label={`${now} ${t.ops.utc}`}>
      <span className="tabular-nums">{now}</span>
      <span className="text-[9px] tracking-widest opacity-70">{t.ops.utc}</span>
    </span>
  );
}
