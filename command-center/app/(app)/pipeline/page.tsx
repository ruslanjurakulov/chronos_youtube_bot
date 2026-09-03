import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, EmptyState, StatusPill } from "@/components/ui";
import { relativeTime, statusTone, timeOfDay } from "@/lib/format";
import type { SystemEventRow } from "@/lib/types";
import { StageStrip, StageLegend, type StageState, type StageView } from "@/components/pipeline/StageStrip";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * The canonical pipeline stages in order. `completed` is the exact event that
 * marks a stage done; `base` is the token whose `.started` / `.failed` variants
 * signal in-progress / error for that same stage.
 */
const STAGES: { key: string; label: string; completed: string; base: string }[] = [
  { key: "topic", label: "Topic", completed: "topic.selected", base: "topic" },
  { key: "research", label: "Research", completed: "research.completed", base: "research" },
  { key: "script", label: "Script", completed: "script.completed", base: "script" },
  { key: "voice", label: "Voice", completed: "voice.completed", base: "voice" },
  { key: "media", label: "Media", completed: "media.completed", base: "media" },
  { key: "thumbnail", label: "Thumbnail", completed: "thumbnail.completed", base: "thumbnail" },
  { key: "render", label: "Render", completed: "render.completed", base: "render" },
  { key: "upload", label: "Upload", completed: "upload.completed", base: "upload" },
  { key: "publish", label: "Publish", completed: "video.published", base: "video" },
];

const HEARTBEAT_MS = 30 * 60 * 1000;

function stageStatus(events: SystemEventRow[], stage: (typeof STAGES)[number]): { state: StageState; ts: string | null } {
  const rel = events.filter(
    (e) => e.event === stage.completed || e.event.startsWith(stage.base + "."),
  );
  if (rel.length === 0) return { state: "WAITING", ts: null };

  const completed = rel.find((e) => e.event === stage.completed || statusTone(e.status) === "ok");
  if (completed) return { state: "COMPLETED", ts: completed.ts };

  const failed = rel.find((e) => e.event.endsWith(".failed") || statusTone(e.status) === "fail");
  if (failed) return { state: "FAILED", ts: failed.ts };

  const running = rel.find((e) => e.event.endsWith(".started") || statusTone(e.status) === "run");
  if (running) return { state: "RUNNING", ts: running.ts };

  return { state: "RUNNING", ts: rel[0].ts };
}

interface VideoPipeline {
  videoId: string;
  stages: StageView[];
  lastActivity: string | null;
  overall: "RUNNING" | "COMPLETED" | "FAILED" | "IN PROGRESS";
}

function derivePipelines(events: SystemEventRow[]): VideoPipeline[] {
  const byVideo = new Map<string, SystemEventRow[]>();
  for (const e of events) {
    if (!e.video_id) continue;
    const list = byVideo.get(e.video_id);
    if (list) list.push(e);
    else byVideo.set(e.video_id, [e]);
  }

  const pipelines: VideoPipeline[] = [];
  for (const [videoId, rows] of byVideo) {
    const stages = STAGES.map<StageView>((s) => {
      const st = stageStatus(rows, s);
      return { key: s.key, label: s.label, state: st.state, ts: st.ts };
    });
    const lastActivity = rows[0]?.ts ?? null;
    const anyFailed = stages.some((s) => s.state === "FAILED");
    const anyRunning = stages.some((s) => s.state === "RUNNING");
    const published = stages[stages.length - 1].state === "COMPLETED";
    const overall: VideoPipeline["overall"] = anyFailed
      ? "FAILED"
      : anyRunning
        ? "RUNNING"
        : published
          ? "COMPLETED"
          : "IN PROGRESS";
    pipelines.push({ videoId, stages, lastActivity, overall });
  }

  // Most recently active videos first.
  return pipelines.sort(
    (a, b) => new Date(b.lastActivity ?? 0).getTime() - new Date(a.lastActivity ?? 0).getTime(),
  );
}

interface SystemPass {
  event: string;
  agent: string | null;
  count: number;
  lastTs: string;
  tone: ReturnType<typeof statusTone>;
}

function deriveSystemPasses(events: SystemEventRow[]): SystemPass[] {
  const byEvent = new Map<string, SystemPass>();
  for (const e of events) {
    if (e.video_id) continue;
    const existing = byEvent.get(e.event);
    if (existing) {
      existing.count += 1;
      if (new Date(e.ts).getTime() > new Date(existing.lastTs).getTime()) {
        existing.lastTs = e.ts;
        existing.tone = statusTone(e.status);
        existing.agent = e.agent;
      }
    } else {
      byEvent.set(e.event, { event: e.event, agent: e.agent, count: 1, lastTs: e.ts, tone: statusTone(e.status) });
    }
  }
  return Array.from(byEvent.values()).sort(
    (a, b) => new Date(b.lastTs).getTime() - new Date(a.lastTs).getTime(),
  );
}

const OVERALL_TONE: Record<VideoPipeline["overall"], "run" | "ok" | "fail" | "idle"> = {
  RUNNING: "run",
  COMPLETED: "ok",
  FAILED: "fail",
  "IN PROGRESS": "idle",
};

export default async function PipelinePage() {
  if (!isSupabaseConfigured) return <NotConfigured />;

  const supabase = await createClient();
  let events: SystemEventRow[] = [];
  let dbError = false;

  if (supabase) {
    const ev = await supabase
      .from("system_events")
      .select("*")
      .order("ts", { ascending: false })
      .limit(500);
    if (ev.error) dbError = true;
    events = (ev.data as SystemEventRow[]) ?? [];
  }

  const pipelines = derivePipelines(events).slice(0, 6);
  const passes = deriveSystemPasses(events);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Pipeline</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">
            Per-video stage flow derived from system_events — {STAGES.length} canonical stages
          </p>
        </div>
        <StageLegend />
      </div>

      <Panel title="Video Pipelines">
        {dbError ? (
          <EmptyState>Could not reach the database. The pipeline view is unavailable right now.</EmptyState>
        ) : pipelines.length === 0 ? (
          <EmptyState>No pipeline activity yet. Each video&apos;s stages appear here as events arrive.</EmptyState>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--color-border)]">
            {pipelines.map((p) => (
              <div key={p.videoId} className="flex flex-col gap-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="mono truncate text-[12px] text-[var(--color-fg)]">{p.videoId}</div>
                  <div className="flex items-center gap-3">
                    <span className="mono text-[10px] text-[var(--color-muted)]">
                      {p.lastActivity ? relativeTime(p.lastActivity) : "N/A"}
                    </span>
                    <StatusPill tone={OVERALL_TONE[p.overall]} label={p.overall} />
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <div className="min-w-[640px]">
                    <StageStrip stages={p.stages} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="System Passes">
        {passes.length === 0 ? (
          <EmptyState>No non-video system events (e.g. intelligence polls) in the recent window.</EmptyState>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {passes.map((p) => {
              const color =
                p.tone === "ok"
                  ? "var(--color-ok)"
                  : p.tone === "fail"
                    ? "var(--color-fail)"
                    : p.tone === "run"
                      ? "var(--color-primary)"
                      : "var(--color-idle)";
              const stale = Date.now() - new Date(p.lastTs).getTime() > HEARTBEAT_MS;
              return (
                <li key={p.event} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <span className="glow-dot size-1.5 shrink-0 rounded-full" style={{ color, background: color }} />
                  <span className="mono w-28 shrink-0 text-[11px] text-[var(--color-primary)]">
                    {p.agent ?? "system"}
                  </span>
                  <span className="truncate text-[var(--color-fg)]">{p.event}</span>
                  <span className="mono ml-auto shrink-0 text-[10px] text-[var(--color-muted)]">
                    {p.count}× · {timeOfDay(p.lastTs)} {stale ? "(stale)" : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
