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
      className="press mono h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 text-[11px] text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:border-[var(--color-primary-dim)]"
    >
      {t.common.signOut}
    </button>
  );
}
