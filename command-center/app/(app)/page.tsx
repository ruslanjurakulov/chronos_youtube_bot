import { redirect } from "next/navigation";

/**
 * The root carries no screen of its own.
 *
 * Every section is reachable at a path that says its name — `/videos`,
 * `/pipeline`, `/time-machine` — and the Command Center is not an exception to
 * that rule just because it happens to be the first screen. It lives at
 * `/command-center`, and `/` sends you there.
 */
export default function RootRedirect() {
  redirect("/command-center");
}
