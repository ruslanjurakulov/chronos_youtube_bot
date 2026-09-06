import type { ReactNode } from "react";

const TONE: Record<string, { fg: string; label: string }> = {
  ok: { fg: "var(--color-ok)", label: "OK" },
  run: { fg: "var(--color-primary)", label: "RUNNING" },
  fail: { fg: "var(--color-fail)", label: "FAILED" },
  warn: { fg: "var(--color-warn)", label: "WARN" },
  idle: { fg: "var(--color-idle)", label: "IDLE" },
};

export function StatusPill({
  tone,
  label,
  live = false,
}: {
  tone: keyof typeof TONE;
  label?: string;
  /** Breathe the dot (for genuinely-active states like a live connection). */
  live?: boolean;
}) {
  const t = TONE[tone] ?? TONE.idle;
  return (
    <span className="inline-flex items-center gap-1.5 mono text-[10px] font-semibold tracking-wider">
      <span
        className={`glow-dot inline-block size-1.5 rounded-full${live ? " live-ring" : ""}`}
        style={{ color: t.fg, background: t.fg }}
      />
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
    <div className="border-t border-[var(--color-border)] pt-4 transition-colors hover:border-[var(--color-primary-dim)]">
      <div className="t-label">{label}</div>
      <div className="t-figure mt-3" style={{ color }}>
        {value}
      </div>
      {sub !== undefined && (
        <div className="mt-2 text-[13px] font-light text-[var(--color-muted)]">{sub}</div>
      )}
    </div>
  );
}

export function Panel({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="section-open">
      <header className="section-head">
        <h2 className="t-panel">{title}</h2>
        {right}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center justify-center px-4 py-14 text-center text-[15px] font-light text-[var(--color-muted)]">
      {children}
    </div>
  );
}
