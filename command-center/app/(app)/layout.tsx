import { NarrowNav } from "@/components/TopNav";
import { Header } from "@/components/Header";
import { CommandPalette } from "@/components/CommandPalette";
import { getUser } from "@/lib/supabase/server";
import { getChannelContext } from "@/lib/channels-server";
import { isSupabaseConfigured } from "@/lib/config";
import { ALL_CHANNELS } from "@/lib/channels";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Middleware already gates access; this reads the user for the header.
  const user = isSupabaseConfigured ? await getUser() : null;
  // Channels for the switcher. Empty before the Phase 5 migration is applied,
  // in which case the switcher renders nothing and the app looks as it did.
  const { channels, selection } = isSupabaseConfigured
    ? await getChannelContext()
    : { channels: [], selection: ALL_CHANNELS };

  return (
    <div className="atmos flex min-h-dvh flex-col">
      <Header userEmail={user?.email} channels={channels} selection={selection} />
      <NarrowNav />
      <main className="pad-page min-w-0 flex-1">{children}</main>
      <CommandPalette />
    </div>
  );
}
