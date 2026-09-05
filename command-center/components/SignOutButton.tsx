"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useI18n } from "@/lib/i18n/context";

export function SignOutButton() {
  const router = useRouter();
  const { t } = useI18n();
  async function signOut() {
    const supabase = createClient();
    if (supabase) await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }
  return (
    <button
      onClick={signOut}
      className="press pill h-9 border border-[var(--color-border)] px-4 text-[13px] font-light text-[var(--color-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-fg)]"
    >
      {t.common.signOut}
    </button>
  );
}
