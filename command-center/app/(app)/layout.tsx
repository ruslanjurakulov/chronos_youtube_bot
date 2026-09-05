import { Sidebar, MobileNav } from "@/components/Sidebar";
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
    <div className="grid-bg atmos flex min-h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header userEmail={user?.email} channels={channels} selection={selection} />
        <MobileNav />
        <main className="pad-page min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
