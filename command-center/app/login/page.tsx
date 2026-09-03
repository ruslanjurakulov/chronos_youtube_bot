"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/config";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const supabase = createClient();
    if (!supabase) {
      setError("Supabase isn't configured — set the NEXT_PUBLIC_SUPABASE_* env vars.");
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="grid-bg flex min-h-dvh items-center justify-center p-6">
      <div className="panel w-full max-w-sm p-6">
        <div className="mono text-sm font-bold tracking-[0.3em] text-[var(--color-primary)]">
          CHRONOS
        </div>
        <div className="mono text-[10px] tracking-widest text-[var(--color-muted)]">
          COMMAND CENTER
        </div>
        <h1 className="mt-4 text-lg font-semibold">Operator sign in</h1>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Monitoring data is private — sign in with your Supabase user.
        </p>

        {!isSupabaseConfigured && (
          <p className="mt-4 mono text-[11px] text-[var(--color-warn)]">
            NOT CONFIGURED — set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
          </p>
        )}

        <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              Email
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              Password
            </span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]"
            />
          </label>
          {error && <p className="mono text-[11px] text-[var(--color-fail)]">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm font-semibold text-[#04121a] transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
