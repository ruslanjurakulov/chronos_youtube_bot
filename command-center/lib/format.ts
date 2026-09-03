/** Formatting helpers. Everything renders "N/A" for null/undefined so the UI
 *  always distinguishes real data from missing data. */

export function num(value: number | null | undefined): string {
  return value === null || value === undefined ? "N/A" : value.toLocaleString();
}

export function decimal(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "N/A" : value.toFixed(digits);
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  const s = Math.round(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function timeOfDay(iso: string | null | undefined): string {
  if (!iso) return "--:--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--:--";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getUTCFullYear() === now.getUTCFullYear() &&
    d.getUTCMonth() === now.getUTCMonth() &&
    d.getUTCDate() === now.getUTCDate()
  );
}

/** Human label + tone for an event/agent status string. */
export function statusTone(status: string | null | undefined): "ok" | "run" | "fail" | "idle" {
  switch ((status ?? "").toLowerCase()) {
    case "completed":
    case "success":
      return "ok";
    case "running":
      return "run";
    case "failed":
    case "error":
      return "fail";
    default:
      return "idle";
  }
}
