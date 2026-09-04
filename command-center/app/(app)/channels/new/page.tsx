import Link from "next/link";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { AddChannelWizard } from "@/components/channels/AddChannelWizard";
import { getDictionary } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function NewChannelPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <div>
        <Link
          href="/channels"
          className="mono text-[10px] uppercase tracking-widest text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          ← {t.channels.title}
        </Link>
        <h1 className="mt-1 text-lg font-semibold">{t.channels.newTitle}</h1>
        <p className="mono text-[11px] text-[var(--color-muted)]">{t.channels.newSubtitle}</p>
      </div>
      <AddChannelWizard />
    </div>
  );
}
