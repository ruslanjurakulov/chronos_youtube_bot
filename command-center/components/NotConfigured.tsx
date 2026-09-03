/**
 * Shown when Supabase env vars are absent. The Command Center never fakes data,
 * so with no backend it says exactly what's missing and how to fix it.
 */
export function NotConfigured() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="panel max-w-lg p-6">
        <div className="mono text-xs font-bold tracking-widest text-[var(--color-warn)]">
          NOT CONFIGURED
        </div>
        <h1 className="mt-2 text-lg font-semibold text-[var(--color-fg)]">
          Supabase connection isn&apos;t set up yet
        </h1>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          The Command Center reads real data from a Supabase project. Set{" "}
          <code className="mono text-[var(--color-primary)]">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="mono text-[var(--color-primary)]">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in
          this app&apos;s environment (Vercel project settings, or{" "}
          <code className="mono">.env.local</code> for local dev).
        </p>
        <p className="mt-3 text-sm text-[var(--color-muted)]">
          Full walkthrough: <code className="mono">docs/SUPABASE.md</code> in the repo root. Until
          then, no data is shown — the dashboard will not invent numbers.
        </p>
      </div>
    </div>
  );
}
