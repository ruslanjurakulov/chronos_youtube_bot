"use client";

import Link from "next/link";

import { useI18n } from "@/lib/i18n/context";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LanguageSelector } from "@/components/LanguageSelector";
import { SignOutButton } from "@/components/SignOutButton";
import { NotificationsCenter } from "@/components/NotificationsCenter";
import { UtcClock } from "@/components/UtcClock";
import { TopNav } from "@/components/TopNav";
import { ChannelSwitcher } from "@/components/ChannelSwitcher";
import { ALL_CHANNELS, type ChannelSelection } from "@/lib/channels";
import type { ChannelRow } from "@/lib/types";

/**
 * One bar, as the approved direction has it: the wordmark and the navigation on
 * the left, the account pill and the operator controls on the right. There is
 * no sidebar any more — nineteen routes in a rail was what made every screen
 * read as an admin console rather than the product.
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
    <header className="sticky top-0 z-30 flex items-center justify-between gap-6 border-b border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-bg)_78%,transparent)] px-[clamp(1.25rem,4vw,100px)] py-5 backdrop-blur-md">
      <div className="flex min-w-0 items-center gap-10">
        <Link
          href="/"
          className="font-display shrink-0 text-xl font-semibold tracking-[-0.02em] text-[var(--color-primary)]"
        >
          {t.brand.name}
        </Link>
        <TopNav />
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <ChannelSwitcher channels={channels} selection={selection} />
        <button
          type="button"
          onClick={openPalette}
          aria-label={t.ops.palettePlaceholder}
          className="press pill hidden h-9 items-center gap-2 border border-[var(--color-border)] px-3.5 text-[var(--color-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-fg)] sm:flex"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="mono pill border border-[var(--color-border)] px-1.5 text-[9px] tracking-wider">⌘K</span>
        </button>
        {userEmail && (
          <span className="hidden max-w-[160px] truncate text-[12px] font-light text-[var(--color-muted)] xl:inline">
            {userEmail}
          </span>
        )}
        <UtcClock />
        <NotificationsCenter />
        <LanguageSelector />
        <ThemeToggle />
        <SignOutButton />
      </div>
    </header>
  );
}
