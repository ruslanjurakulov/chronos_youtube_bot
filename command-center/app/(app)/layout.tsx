import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { NarrowNav } from "@/components/TopNav";
import { NightSky } from "@/components/NightSky";
import { Header } from "@/components/Header";
import { CommandPalette } from "@/components/CommandPalette";
import { getChannelContext } from "@/lib/channels-server";
import { isSupabaseConfigured } from "@/lib/config";
import { ALL_CHANNELS, PATH_HEADER, selectionToSlug } from "@/lib/channels";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Channels for the switcher. Empty before the Phase 5 migration is applied,
  // in which case the switcher renders nothing and the app looks as it did.
  const { channels, selection } = isSupabaseConfigured
    ? await getChannelContext()
    : { channels: [], selection: ALL_CHANNELS };

  // Keep the address bar honest. A URL naming a channel that does not exist
  // (deleted, renamed, mistyped, or not visible to this user) resolves to every
  // channel — so the URL is corrected to say so, rather than left claiming a
  // channel the screen below is not showing.
  const path = (await headers()).get(PATH_HEADER);
  if (path) {
    const [, slug, ...rest] = path.split("/");
    const honest = selectionToSlug(selection);
    if (slug && slug !== honest) redirect(["", honest, ...rest].join("/"));
  }

  return (
    <div className="atmos relative flex min-h-dvh flex-col">
      <NightSky />
      <div className="relative z-10 flex min-h-dvh flex-col">
        <Header channels={channels} selection={selection} />
        <NarrowNav />
        <main className="pad-page min-w-0 flex-1">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
