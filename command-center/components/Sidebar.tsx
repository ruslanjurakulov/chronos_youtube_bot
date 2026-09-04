"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/lib/i18n/context";
import type { Dictionary } from "@/lib/i18n";

type NavKey = keyof Dictionary["nav"];
const NAV: { href: string; key: NavKey; glyph: string }[] = [
  { href: "/", key: "command", glyph: "◎" },
  { href: "/channels", key: "channels", glyph: "◉" },
  { href: "/videos", key: "videos", glyph: "▦" },
  { href: "/pipeline", key: "pipeline", glyph: "⌗" },
  { href: "/agents", key: "agents", glyph: "⚙" },
  { href: "/jobs", key: "jobs", glyph: "≡" },
  { href: "/topics", key: "topics", glyph: "◈" },
  { href: "/analytics", key: "analytics", glyph: "◔" },
  { href: "/intelligence", key: "intelligence", glyph: "✦" },
  { href: "/decisions", key: "decisions", glyph: "◆" },
  { href: "/learning", key: "learning", glyph: "∿" },
  { href: "/memory", key: "memory", glyph: "❖" },
  { href: "/autonomy", key: "autonomy", glyph: "⟠" },
  { href: "/feedback", key: "feedback", glyph: "⟳" },
  { href: "/timemachine", key: "timeMachine", glyph: "◷" },
  { href: "/errors", key: "errors", glyph: "⚠" },
  { href: "/logs", key: "logs", glyph: "☰" },
  { href: "/integrations", key: "integrations", glyph: "⇄" },
];

/** True when `href` is the active route (exact for "/", prefix otherwise). */
function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

export function Sidebar() {
  const { t } = useI18n();
  const isActive = useIsActive();

  return (
    <aside className="hidden md:flex md:w-56 shrink-0 flex-col gap-1 border-r border-[var(--color-border)] bg-[var(--color-panel)] p-3">
      <div className="mb-5 px-2 pt-1">
        <div className="font-display text-base font-bold tracking-[0.28em] text-[var(--color-primary)]">
          {t.brand.name}
        </div>
        <div className="mono text-[10px] tracking-[0.25em] text-[var(--color-muted)]">
          {t.brand.tagline}
        </div>
      </div>
      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className="press group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors"
              style={{
                background: active ? "var(--color-panel-2)" : "transparent",
                color: active ? "var(--color-fg)" : "var(--color-muted)",
              }}
            >
              <span
                aria-hidden
                className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full transition-all"
                style={{ background: active ? "var(--color-primary)" : "transparent" }}
              />
              <span
                className="w-4 text-center transition-colors"
                style={{ color: active ? "var(--color-primary)" : "var(--color-idle)" }}
              >
                {item.glyph}
              </span>
              <span className="group-hover:text-[var(--color-fg)]">{t.nav[item.key]}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

/** Horizontal nav for narrow screens. */
export function MobileNav() {
  const { t } = useI18n();
  const isActive = useIsActive();
  return (
    <nav className="md:hidden flex gap-1 overflow-x-auto border-b border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
      {NAV.map((item) => {
        const active = isActive(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className="press whitespace-nowrap rounded-md px-3 py-1.5 text-xs transition-colors"
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
