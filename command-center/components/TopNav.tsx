"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n/context";
import type { Dictionary } from "@/lib/i18n";

type NavKey = Exclude<keyof Dictionary["nav"], "more">;

/**
 * Navigation lives in one horizontal bar, as the approved direction has it.
 *
 * Nineteen routes will not fit in a bar, and cutting routes to make them fit
 * would be a product decision disguised as a design one. So the six that carry
 * the daily loop stay in the bar and the rest sit behind "More" — every route
 * is still one click away, and ⌘K still reaches all of them by name.
 */
const PRIMARY: { href: string; key: NavKey }[] = [
  { href: "/", key: "command" },
  { href: "/channels", key: "channels" },
  { href: "/videos", key: "videos" },
  { href: "/pipeline", key: "pipeline" },
  { href: "/analytics", key: "analytics" },
  { href: "/intelligence", key: "intelligence" },
];

const SECONDARY: { href: string; key: NavKey }[] = [
  { href: "/agents", key: "agents" },
  { href: "/jobs", key: "jobs" },
  { href: "/topics", key: "topics" },
  { href: "/measure", key: "measure" },
  { href: "/decisions", key: "decisions" },
  { href: "/learning", key: "learning" },
  { href: "/memory", key: "memory" },
  { href: "/autonomy", key: "autonomy" },
  { href: "/feedback", key: "feedback" },
  { href: "/timemachine", key: "timeMachine" },
  { href: "/errors", key: "errors" },
  { href: "/logs", key: "logs" },
  { href: "/integrations", key: "integrations" },
];

export const ALL_NAV = [...PRIMARY, ...SECONDARY];

/** True when `href` is the active route (exact for "/", prefix otherwise). */
function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

export function TopNav() {
  const { t } = useI18n();
  const isActive = useIsActive();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const moreActive = SECONDARY.some((i) => isActive(i.href));

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <nav className="hidden items-center gap-7 lg:flex">
      {PRIMARY.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="nav-link"
            data-active={active ? "true" : undefined}
          >
            {t.nav[item.key]}
          </Link>
        );
      })}

      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="menu"
          aria-expanded={open}
          className="nav-link flex items-center gap-1.5"
          data-active={moreActive ? "true" : undefined}
        >
          {t.nav.more}
          <span aria-hidden className="text-[10px]">
            ▾
          </span>
        </button>

        {open && (
          <div
            role="menu"
            className="drawer-enter absolute left-0 z-50 mt-4 w-60 rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-2 shadow-[var(--shadow-elevated)]"
            style={{ ["--from" as string]: "-8px" }}
          >
            {SECONDARY.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  role="menuitem"
                  onClick={() => setOpen(false)}
                  className="pill block px-4 py-2.5 text-[14px] font-light transition-colors hover:bg-[var(--color-panel-2)]"
                  style={{ color: active ? "var(--color-primary)" : "var(--color-fg)" }}
                >
                  {t.nav[item.key]}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </nav>
  );
}

/** Every route as a scrolling strip, for screens too narrow for the bar. */
export function NarrowNav() {
  const { t } = useI18n();
  const isActive = useIsActive();
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-[var(--color-border)] px-[clamp(1.25rem,4vw,100px)] py-3 lg:hidden">
      {ALL_NAV.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="press pill whitespace-nowrap px-4 py-2 text-sm font-light transition-colors"
            style={{
              background: active ? "var(--color-panel-2)" : "transparent",
              color: active ? "var(--color-primary)" : "var(--color-muted)",
            }}
          >
            {t.nav[item.key]}
          </Link>
        );
      })}
    </nav>
  );
}
