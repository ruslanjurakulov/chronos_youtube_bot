import { NarrowNav } from "@/components/TopNav";
import { Header } from "@/components/Header";
import { CommandPalette } from "@/components/CommandPalette";
import { getChannelContext } from "@/lib/channels-server";
import { isSupabaseConfigured } from "@/lib/config";
import { ALL_CHANNELS } from "@/lib/channels";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Channels for the switcher. Empty before the Phase 5 migration is applied,
  // in which case the switcher renders nothing and the app looks as it did.
  const { channels, selection } = isSupabaseConfigured
    ? await getChannelContext()
    : { channels: [], selection: ALL_CHANNELS };

  return (
    <div className="atmos flex min-h-dvh flex-col">
      <Header channels={channels} selection={selection} />
      <NarrowNav />
      <main className="pad-page min-w-0 flex-1">{children}</main>
      <CommandPalette />
    </div>
  );
}
