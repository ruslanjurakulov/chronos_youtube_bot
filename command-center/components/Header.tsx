"use client";

import { useI18n } from "@/lib/i18n/context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LanguageSelector } from "@/components/LanguageSelector";
import { SignOutButton } from "@/components/SignOutButton";

/**
 * App header: brand wordmark, then the operator controls — language, theme,
 * signed-in user, sign out. Kept deliberately sparse; primary navigation lives
 * in the sidebar (and the mobile strip below this bar).
 */
export function Header({ userEmail }: { userEmail?: string | null }) {
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-panel)_88%,transparent)] px-4 py-2.5 backdrop-blur-md">
      <div className="flex items-baseline gap-2 md:hidden">
        <span className="font-display text-sm font-bold tracking-[0.22em] text-[var(--color-primary)]">
          {t.brand.name}
        </span>
      </div>
      <div className="mono hidden text-[11px] tracking-[0.28em] text-[var(--color-muted)] md:block">
        {t.brand.name} · {t.brand.operations}
      </div>

      <div className="flex items-center gap-2">
        {userEmail && (
          <span className="mono hidden max-w-[180px] truncate text-[11px] text-[var(--color-muted)] sm:inline lg:max-w-none">
            {userEmail}
          </span>
        )}
        <LanguageSelector />
        <ThemeToggle />
        <SignOutButton />
      </div>
    </header>
  );
}
