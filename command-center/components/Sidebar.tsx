import Link from "next/link";

const NAV: { href: string; label: string; glyph: string }[] = [
  { href: "/", label: "Command Center", glyph: "◎" },
  { href: "/videos", label: "Videos", glyph: "▦" },
  { href: "/pipeline", label: "Pipeline", glyph: "⌗" },
  { href: "/agents", label: "Agents", glyph: "⚙" },
  { href: "/jobs", label: "Jobs", glyph: "≡" },
  { href: "/topics", label: "Topics", glyph: "◈" },
  { href: "/analytics", label: "Analytics", glyph: "◔" },
  { href: "/feedback", label: "Feedback Loop", glyph: "⟳" },
  { href: "/errors", label: "Errors", glyph: "⚠" },
  { href: "/logs", label: "Logs", glyph: "☰" },
  { href: "/integrations", label: "Integrations", glyph: "⇄" },
];

export function Sidebar() {
  return (
    <aside className="hidden md:flex md:w-56 shrink-0 flex-col gap-1 border-r border-[var(--color-border)] bg-[var(--color-panel)] p-3">
      <div className="mb-4 px-2 pt-1">
        <div className="mono text-sm font-bold tracking-[0.3em] text-[var(--color-primary)]">
          CHRONOS
        </div>
        <div className="mono text-[10px] tracking-widest text-[var(--color-muted)]">
          COMMAND CENTER
        </div>
      </div>
      <nav className="flex flex-col gap-0.5">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-[var(--color-muted)] transition-colors hover:bg-[var(--color-panel-2)] hover:text-[var(--color-fg)]"
          >
            <span className="w-4 text-center text-[var(--color-primary)]">{item.glyph}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}

/** Horizontal nav for narrow screens. */
export function MobileNav() {
  return (
    <nav className="md:hidden flex gap-1 overflow-x-auto border-b border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="whitespace-nowrap rounded-md px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
