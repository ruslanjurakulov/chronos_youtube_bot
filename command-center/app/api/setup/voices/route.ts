import { NextResponse } from "next/server";
import { getUser } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * List the ElevenLabs voices this account can actually use.
 *
 * The wizard used to ask for a voice id as free text. Nobody knows an
 * ElevenLabs voice id by heart, so what got typed was a plausible-looking
 * number — `16516516145` — which the form accepted, the database stored, and
 * the pipeline discovered four Gemini calls into a run. Offering the real
 * voices removes the guess: you cannot mistype a value you picked from a list.
 *
 * Same contract as the YouTube route next door: the key arrives in the body,
 * is used for exactly one upstream call, and is dropped when the handler
 * returns. It is not stored, not cached, not logged, and not echoed back. The
 * response carries only what the picker needs to draw itself.
 */
export async function POST(request: Request) {
  const user = await getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { apiKey?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "bad_request" }, { status: 400 });
  }

  const apiKey = (body.apiKey ?? "").trim();
  if (!apiKey) return NextResponse.json({ error: "missing_key" }, { status: 400 });

  let res: Response;
  try {
    res = await fetch("https://api.elevenlabs.io/v1/voices", {
      headers: { "xi-api-key": apiKey },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "elevenlabs_unreachable" }, { status: 502 });
  }

  if (res.status === 401) {
    // 401 covers three different situations that need three different fixes,
    // so the caller gets ElevenLabs' own code rather than a flat "rejected":
    // invalid_api_key is a wrong key, quota_exceeded is an account out of
    // characters, detected_unusual_activity is a blocked free tier.
    let reason = "";
    try {
      const detail = ((await res.json()) as { detail?: { status?: string } }).detail;
      reason = detail?.status ?? "";
    } catch {
      /* an unparseable body is still a 401 */
    }
    return NextResponse.json({ error: "key_rejected", reason }, { status: 400 });
  }
  if (!res.ok) return NextResponse.json({ error: "elevenlabs_unavailable" }, { status: 502 });

  const data = (await res.json()) as {
    voices?: {
      voice_id: string;
      name?: string;
      category?: string;
      preview_url?: string;
      labels?: Record<string, string>;
    }[];
  };

  const voices = (data.voices ?? []).map((v) => ({
    voiceId: v.voice_id,
    name: v.name ?? v.voice_id,
    category: v.category ?? "",
    previewUrl: v.preview_url ?? "",
    // Accent, age, gender and use case, as ElevenLabs labels them. This is what
    // makes two voices distinguishable in a dropdown of thirty.
    labels: Object.values(v.labels ?? {}).filter(Boolean).join(" · "),
  }));

  return NextResponse.json({ voices });
}
