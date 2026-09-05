"use client";

import { useI18n } from "@/lib/i18n/context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LanguageSelector } from "@/components/LanguageSelector";
import { SignOutButton } from "@/components/SignOutButton";
import { NotificationsCenter } from "@/components/NotificationsCenter";
import { UtcClock } from "@/components/UtcClock";
import { ChannelSwitcher } from "@/components/ChannelSwitcher";
import { ALL_CHANNELS, type ChannelSelection } from "@/lib/channels";
import type { ChannelRow } from "@/lib/types";

/**
 * App header: brand wordmark, a UTC clock, the channel switcher, a
 * command-palette search trigger, notifications, then the operator controls —
 * language, theme, sign out. Primary navigation lives in the sidebar (and the
 * mobile strip below).
 */
export function Header({
  userEmail,
  channels = [],
  selection = ALL_CHANNELS,
}: {
  userEmail?: string | null;
  channels?: ChannelRow[];
  selection?: ChannelSelection;
}) {
  const { t } = useI18n();

  function openPalette() {
    window.dispatchEvent(new CustomEvent("chronos:palette-open"));
  }

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-bg)_78%,transparent)] px-[clamp(1.25rem,4vw,100px)] py-5 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <span className="font-display text-lg font-semibold tracking-[-0.02em] text-[var(--color-primary)] md:hidden">
          {t.brand.name}
        </span>
        <span className="hidden text-[12px] font-light tracking-[0.16em] text-[var(--color-muted)] md:inline">
          {t.brand.name} · {t.brand.operations}
        </span>
        <UtcClock />
      </div>

      <div className="flex items-center gap-2">
        <ChannelSwitcher channels={channels} selection={selection} />
        <button
          type="button"
          onClick={openPalette}
          aria-label={t.ops.palettePlaceholder}
          className="press pill hidden h-9 items-center gap-2 border border-[var(--color-border)] px-3.5 text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:border-[var(--color-primary-dim)] sm:flex"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="mono pill border border-[var(--color-border)] px-1.5 text-[9px] tracking-wider">⌘K</span>
        </button>
        {userEmail && (
          <span className="mono hidden max-w-[160px] truncate text-[11px] text-[var(--color-muted)] xl:inline">{userEmail}</span>
        )}
        <NotificationsCenter />
        <LanguageSelector />
        <ThemeToggle />
        <SignOutButton />
      </div>
    </header>
  );
}
