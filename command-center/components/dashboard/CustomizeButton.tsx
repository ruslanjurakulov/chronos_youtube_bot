"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n/context";

/** Toggles dashboard customize mode by broadcasting a window event that each
 *  Widget listens for — no context/prop threading, so server-rendered widget
 *  content still works. Layout choices persist per-device in localStorage. */
export function CustomizeButton() {
  const { t } = useI18n();
  const [on, setOn] = useState(false);

  function toggle() {
    const next = !on;
    setOn(next);
    window.dispatchEvent(new CustomEvent("chronos:customize", { detail: { on: next } }));
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="press mono h-7 rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 text-[10px] uppercase tracking-widest text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:border-[var(--color-primary-dim)]"
    >
      {on ? t.ops.customizeDone : t.ops.customize}
    </button>
  );
}
