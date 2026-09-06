import { redirect } from "next/navigation";

/**
 * A channel on its own names no screen — it names a lens. Landing on one sends
 * you to that channel's Command Center, which is what "open this channel"
 * means.
 */
export default async function ChannelIndex({
  params,
}: {
  params: Promise<{ channel: string }>;
}) {
  const { channel } = await params;
  redirect(`/${channel}/command-center`);
}
