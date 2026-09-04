"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useI18n } from "@/lib/i18n/context";
import { fmt } from "@/lib/i18n";
import { isValidChannelId, slugifyChannelId } from "@/lib/channels";

/**
 * Guided channel creation.
 *
 * Two things are deliberate:
 *
 * 1. **The channel is created PAUSED**, always, with no option here to create
 *    it active. Creating a channel must never start publishing; activating is a
 *    separate, explicit act on the Channels page once YouTube is connected.
 * 2. **The Connect YouTube step hands over instructions, not a token field.**
 *    A refresh token must never pass through the browser, so there is nowhere
 *    to paste one: the step names the command to run on a trusted machine and
 *    the GitHub secret the resulting token belongs in. The connection status
 *    that appears afterwards is reported by the bot, which is the only party
 *    that can actually see the credential.
 *
 * The write goes to `channels` only, via the authenticated insert policy added
 * by migration 0001. No data table is writable from here.
 */

const STEPS = [
  "identity",
  "niche",
  "content",
  "voice",
  "visual",
  "schedule",
  "connect",
  "activate",
] as const;

type Step = (typeof STEPS)[number];

export function AddChannelWizard() {
  const { t } = useI18n();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [channelId, setChannelId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [niche, setNiche] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [nicheRules, setNicheRules] = useState("");
  const [language, setLanguage] = useState("English");
  const [duration, setDuration] = useState(300);
  const [ttsProvider, setTtsProvider] = useState("edge");
  const [edgeVoice, setEdgeVoice] = useState("en-US-ChristopherNeural");
  const [elevenVoice, setElevenVoice] = useState("");
  const [visualStyle, setVisualStyle] = useState("");
  const [competitors, setCompetitors] = useState("");
  const [hour, setHour] = useState<number | "">(15);
  const [scheduleEnabled, setScheduleEnabled] = useState(true);
  const [credentialRef, setCredentialRef] = useState("");
  const [youtubeChannelId, setYoutubeChannelId] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);

  const effectiveId = idTouched ? channelId : slugifyChannelId(name);
  const idValid = isValidChannelId(effectiveId);
  const secret = useMemo(() => {
    const key = credentialRef || effectiveId || "channel";
    return "CHRONOS_YT_TOKEN_" + key.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }, [credentialRef, effectiveId]);

  const current: Step = STEPS[step];
  const canAdvance = current === "identity" ? Boolean(name.trim()) && idValid : true;

  async function create() {
    const supabase = createClient();
    if (!supabase) return;
    setBusy(true);
    setError(null);
    const now = new Date().toISOString();
    const { error: err } = await supabase.from("channels").insert({
      channel_id: effectiveId,
      name: name.trim(),
      niche: niche.trim(),
      // Not negotiable: a new channel does not publish until a human says so.
      status: "PAUSED",
      agent_config: {
        language,
        target_duration_seconds: duration,
        tts_provider: ttsProvider,
        edge_tts_voice: edgeVoice,
        ...(elevenVoice ? { elevenlabs_voice_id: elevenVoice } : {}),
        ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {}),
        ...(nicheRules.trim() ? { niche_rules: nicheRules.trim() } : {}),
        ...(visualStyle.trim() ? { visual_style_prompt: visualStyle.trim() } : {}),
        // Always sent, even when empty: an explicit [] means "watch nobody",
        // which is not the same as inheriting the process-wide env var.
        competitor_channel_ids: competitors
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      },
      schedule_config: {
        publish_hour_utc: hour === "" ? null : Number(hour),
        enabled: scheduleEnabled,
      },
      // A reference only — the token itself never reaches this app.
      credential_ref: {
        provider: "youtube",
        ref: credentialRef.trim() || effectiveId,
        youtube_channel_id: youtubeChannelId.trim(),
      },
      created_at: now,
      updated_at: now,
    });
    setBusy(false);
    if (err) {
      setError(err.message);
      return;
    }
    setCreated(true);
    router.refresh();
  }

  if (created) {
    return (
      <div className="panel flex flex-col items-start gap-3 p-6">
        <p className="text-sm text-[var(--color-ok)]">{t.channels.created}</p>
        <p className="text-[12px] leading-relaxed text-[var(--color-muted)]">
          {fmt(t.channels.connectHint, { id: effectiveId, secret })}
        </p>
        <button
          type="button"
          onClick={() => router.push("/channels")}
          className="press rounded-md border border-[var(--color-primary-dim)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[var(--color-primary)]"
        >
          {t.channels.title} →
        </button>
      </div>
    );
  }

  return (
    <div className="panel flex flex-col gap-4 p-5">
      <ol className="flex flex-wrap gap-1.5">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === step ? "step" : undefined}
            className="mono rounded px-2 py-0.5 text-[9px] uppercase tracking-widest"
            style={{
              background: i === step ? "var(--color-panel-2)" : "transparent",
              color:
                i === step
                  ? "var(--color-primary)"
                  : i < step
                    ? "var(--color-fg)"
                    : "var(--color-muted)",
            }}
          >
            {i + 1}. {stepLabel(s, t)}
          </li>
        ))}
      </ol>

      <div className="flex min-h-[190px] flex-col gap-3">
        {current === "identity" && (
          <>
            <Field label={t.channels.name}>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Extinct World"
                className={inputClass}
              />
            </Field>
            <Field label={t.channels.id} hint={t.channels.idHint}>
              <input
                value={effectiveId}
                onChange={(e) => {
                  setIdTouched(true);
                  setChannelId(e.target.value);
                }}
                placeholder="extinct-world"
                className={inputClass}
                aria-invalid={Boolean(effectiveId) && !idValid}
              />
            </Field>
          </>
        )}

        {current === "niche" && (
          <Field label={t.channels.niche}>
            <input
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              placeholder="Prehistoric History"
              className={inputClass}
            />
          </Field>
        )}

        {current === "content" && (
          <>
            <Field label={t.channels.systemPrompt}>
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={3}
                className={inputClass}
              />
            </Field>
            <Field label={t.channels.contentRules}>
              <textarea
                value={nicheRules}
                onChange={(e) => setNicheRules(e.target.value)}
                rows={2}
                className={inputClass}
              />
            </Field>
            <Field label={t.channels.competitors} hint={t.channels.competitorsHint}>
              <input
                value={competitors}
                onChange={(e) => setCompetitors(e.target.value)}
                placeholder="UCxxxxxxxx, UCyyyyyyyy"
                className={inputClass}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t.channels.language}>
                <input value={language} onChange={(e) => setLanguage(e.target.value)} className={inputClass} />
              </Field>
              <Field label={t.channels.targetDuration}>
                <input
                  type="number"
                  min={60}
                  max={3600}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value) || 300)}
                  className={inputClass}
                />
              </Field>
            </div>
          </>
        )}

        {current === "voice" && (
          <>
            <Field label="TTS">
              <select value={ttsProvider} onChange={(e) => setTtsProvider(e.target.value)} className={inputClass}>
                <option value="edge">edge</option>
                <option value="elevenlabs">elevenlabs</option>
              </select>
            </Field>
            {ttsProvider === "edge" ? (
              <Field label={t.channels.voice}>
                <input value={edgeVoice} onChange={(e) => setEdgeVoice(e.target.value)} className={inputClass} />
              </Field>
            ) : (
              <Field label={t.channels.voice}>
                <input
                  value={elevenVoice}
                  onChange={(e) => setElevenVoice(e.target.value)}
                  placeholder="voice id"
                  className={inputClass}
                />
              </Field>
            )}
          </>
        )}

        {current === "visual" && (
          <Field label={t.channels.visualStyle}>
            <textarea
              value={visualStyle}
              onChange={(e) => setVisualStyle(e.target.value)}
              rows={3}
              placeholder="Cinematic prehistoric documentary: primeval forests, volcanic skies, fossil beds."
              className={inputClass}
            />
          </Field>
        )}

        {current === "schedule" && (
          <>
            <Field label={t.channels.scheduleHour}>
              <input
                type="number"
                min={0}
                max={23}
                value={hour}
                onChange={(e) => setHour(e.target.value === "" ? "" : Number(e.target.value))}
                className={inputClass}
              />
            </Field>
            <label className="flex items-center gap-2 text-[12px] text-[var(--color-fg)]">
              <input
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(e) => setScheduleEnabled(e.target.checked)}
              />
              {t.channels.scheduleEnabled}
            </label>
          </>
        )}

        {current === "connect" && (
          <>
            <Field label="credential ref">
              <input
                value={credentialRef}
                onChange={(e) => setCredentialRef(e.target.value)}
                placeholder={effectiveId}
                className={inputClass}
              />
            </Field>
            <Field label={`${t.channels.youtube} channel id`}>
              <input
                value={youtubeChannelId}
                onChange={(e) => setYoutubeChannelId(e.target.value)}
                placeholder="UC…"
                className={inputClass}
              />
            </Field>
            <p className="text-[12px] leading-relaxed text-[var(--color-muted)]">
              {fmt(t.channels.connectHint, { id: effectiveId || "…", secret })}
            </p>
          </>
        )}

        {current === "activate" && (
          <p className="text-[12px] leading-relaxed text-[var(--color-muted)]">{t.channels.activateHint}</p>
        )}
      </div>

      {error && <p className="mono text-[11px] text-[var(--color-fail)]">{t.channels.createFailed}: {error}</p>}

      <div className="flex items-center justify-between gap-3 border-t border-[var(--color-border)] pt-3">
        <button
          type="button"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0 || busy}
          className="press rounded-md border border-[var(--color-border)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[var(--color-muted)] disabled:opacity-40"
        >
          {t.channels.back}
        </button>
        {step < STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            disabled={!canAdvance}
            className="press rounded-md border border-[var(--color-primary-dim)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[var(--color-primary)] disabled:opacity-40"
          >
            {t.channels.next}
          </button>
        ) : (
          <button
            type="button"
            onClick={create}
            disabled={busy || !idValid || !name.trim()}
            className="press rounded-md border border-[var(--color-primary-dim)] bg-[var(--color-panel-2)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[var(--color-primary)] disabled:opacity-40"
          >
            {busy ? t.channels.creating : t.channels.create}
          </button>
        )}
      </div>
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-2.5 py-1.5 text-[13px] text-[var(--color-fg)] outline-none focus-visible:border-[var(--color-primary-dim)]";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="mono text-[9px] uppercase tracking-widest text-[var(--color-muted)]">{label}</span>
      {children}
      {hint && <span className="text-[10px] text-[var(--color-muted)]">{hint}</span>}
    </label>
  );
}

type Dict = ReturnType<typeof useI18n>["t"];

function stepLabel(step: Step, t: Dict): string {
  switch (step) {
    case "identity":
      return t.channels.stepIdentity;
    case "niche":
      return t.channels.stepNiche;
    case "content":
      return t.channels.stepContent;
    case "voice":
      return t.channels.stepVoice;
    case "visual":
      return t.channels.stepVisual;
    case "schedule":
      return t.channels.stepSchedule;
    case "connect":
      return t.channels.stepConnect;
    default:
      return t.channels.stepActivate;
  }
}
