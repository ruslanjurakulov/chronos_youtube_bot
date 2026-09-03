import type { ReactNode } from "react";

const TONE: Record<string, { fg: string; label: string }> = {
  ok: { fg: "var(--color-ok)", label: "OK" },
  run: { fg: "var(--color-primary)", label: "RUNNING" },
  fail: { fg: "var(--color-fail)", label: "FAILED" },
  warn: { fg: "var(--color-warn)", label: "WARN" },
  idle: { fg: "var(--color-idle)", label: "IDLE" },
};

export function StatusPill({ tone, label }: { tone: keyof typeof TONE; label?: string }) {
  const t = TONE[tone] ?? TONE.idle;
  return (
    <span className="inline-flex items-center gap-1.5 mono text-[10px] font-semibold tracking-wider">
      <span className="glow-dot inline-block size-1.5 rounded-full" style={{ color: t.fg, background: t.fg }} />
      <span style={{ color: t.fg }}>{label ?? t.label}</span>
    </span>
  );
}

export function StatCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: keyof typeof TONE;
}) {
  const color = tone ? (TONE[tone]?.fg ?? "var(--color-fg)") : "var(--color-fg)";
  return (
    <div className="panel p-4">
      <div className="mono text-[10px] font-semibold uppercase tracking-widest text-[var(--color-muted)]">
        {label}
      </div>
      <div className="mt-1.5 mono text-2xl font-bold tabular-nums" style={{ color }}>
        {value}
      </div>
      {sub !== undefined && (
        <div className="mt-0.5 mono text-[11px] text-[var(--color-muted)]">{sub}</div>
      )}
    </div>
  );
}

export function Panel({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="panel flex flex-col overflow-hidden">
      <header className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5">
        <h2 className="mono text-xs font-bold uppercase tracking-widest text-[var(--color-fg)]">{title}</h2>
        {right}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center justify-center p-8 text-center mono text-xs text-[var(--color-muted)]">
      {children}
    </div>
  );
}
