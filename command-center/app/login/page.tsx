"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/config";
import { useI18n } from "@/lib/i18n/context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LanguageSelector } from "@/components/LanguageSelector";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const supabase = createClient();
    if (!supabase) {
      setError(t.auth.notConfiguredErr);
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      // Supabase's own message (e.g. "Invalid login credentials") — surfaced verbatim.
      setError(error.message);
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="grid-bg relative flex min-h-dvh items-center justify-center p-6">
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <LanguageSelector />
        <ThemeToggle />
      </div>

      <div className="reveal panel w-full max-w-sm p-6">
        <div className="font-display text-sm font-bold tracking-[0.3em] text-[var(--color-primary)]">
          {t.brand.name}
        </div>
        <div className="mono text-[10px] tracking-[0.25em] text-[var(--color-muted)]">
          {t.brand.tagline}
        </div>
        <h1 className="mt-4 text-lg font-semibold">{t.auth.signInTitle}</h1>
        <p className="mt-1 text-xs text-[var(--color-muted)]">{t.auth.signInSub}</p>

        {!isSupabaseConfigured && (
          <p className="mt-4 mono text-[11px] text-[var(--color-warn)]">{t.auth.notConfigured}</p>
        )}

        <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              {t.auth.email}
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm outline-none transition-colors focus:border-[var(--color-primary)]"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              {t.auth.password}
            </span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-2 text-sm outline-none transition-colors focus:border-[var(--color-primary)]"
            />
          </label>
          {error && <p className="mono text-[11px] text-[var(--color-fail)]">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="press mt-1 rounded-md bg-[var(--color-primary)] px-3 py-2 text-sm font-semibold text-[var(--color-on-accent)] hover:opacity-90 disabled:opacity-50"
          >
            {busy ? t.auth.signingIn : t.auth.signIn}
          </button>
        </form>
      </div>
    </main>
  );
}
