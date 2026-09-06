import { redirect } from "next/navigation";
import { ALL_CHANNELS_SLUG } from "@/lib/channels";

/**
 * The root names neither a channel nor a screen, so it stands for nothing.
 *
 * In practice the middleware redirects "/" before routing gets here, using the
 * channel you last looked at. This is the fallback for the case where it does
 * not run — every channel, Command Center.
 */
export default function RootRedirect() {
  redirect(`/${ALL_CHANNELS_SLUG}/command-center`);
}
