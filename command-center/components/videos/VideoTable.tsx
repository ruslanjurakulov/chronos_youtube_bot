"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { num, relativeTime } from "@/lib/format";
import type { VideoWithMetrics } from "@/app/(app)/videos/page";

const PRIVACY_FILTERS = ["all", "public", "unlisted", "private"] as const;
type PrivacyFilter = (typeof PRIVACY_FILTERS)[number];

/**
 * Client-side searchable / filterable table for the video library. Receives the
 * server-fetched rows (video + latest metrics snapshot) as props and never
 * fetches on its own — it only filters what the server already resolved.
 */
export function VideoTable({ rows }: { rows: VideoWithMetrics[] }) {
  const [query, setQuery] = useState("");
  const [privacy, setPrivacy] = useState<PrivacyFilter>("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (privacy !== "all" && (r.privacy ?? "").toLowerCase() !== privacy) return false;
      if (!q) return true;
      return (
        (r.title ?? "").toLowerCase().includes(q) ||
        (r.topic ?? "").toLowerCase().includes(q) ||
        r.video_id.toLowerCase().includes(q)
      );
    });
  }, [rows, query, privacy]);

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] px-4 py-2.5">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search title, topic, id…"
          className="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-panel-2)] px-3 py-1.5 text-sm text-[var(--color-fg)] outline-none placeholder:text-[var(--color-muted)] focus:border-[var(--color-primary-dim)]"
        />
        <div className="flex gap-1">
          {PRIVACY_FILTERS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPrivacy(p)}
              className="mono rounded-md px-2.5 py-1.5 text-[10px] uppercase tracking-widest transition-colors"
              style={{
                background: privacy === p ? "var(--color-panel-2)" : "transparent",
                color: privacy === p ? "var(--color-primary)" : "var(--color-muted)",
                border:
                  privacy === p
                    ? "1px solid var(--color-primary-dim)"
                    : "1px solid var(--color-border)",
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              <th className="px-4 py-2 font-semibold">Title</th>
              <th className="px-4 py-2 font-semibold">Topic</th>
              <th className="px-4 py-2 font-semibold">Published</th>
              <th className="px-4 py-2 font-semibold">Privacy</th>
              <th className="px-4 py-2 text-right font-semibold">Views</th>
              <th className="px-4 py-2 text-right font-semibold">Likes</th>
              <th className="px-4 py-2 text-right font-semibold">Comments</th>
              <th className="px-4 py-2 text-right font-semibold">Avg view (s)</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-4 py-8 text-center mono text-xs text-[var(--color-muted)]"
                >
                  No videos match the current filter.
                </td>
              </tr>
            ) : (
              filtered.map((v) => (
                <tr
                  key={v.video_id}
                  className="border-b border-[var(--color-border)]/50 transition-colors hover:bg-[var(--color-panel-2)]"
                >
                  <td className="px-4 py-2 text-[var(--color-fg)]">
                    <Link
                      href={`/videos/${v.video_id}`}
                      className="hover:text-[var(--color-primary)]"
                    >
                      {v.title ?? v.video_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-[var(--color-muted)]">{v.topic ?? "N/A"}</td>
                  <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">
                    {relativeTime(v.published_at)}
                  </td>
                  <td className="px-4 py-2 mono text-[11px] text-[var(--color-muted)]">
                    {v.privacy ?? "N/A"}
                  </td>
                  <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-fg)]">
                    {num(v.metrics?.views)}
                  </td>
                  <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                    {num(v.metrics?.likes)}
                  </td>
                  <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                    {num(v.metrics?.comment_count)}
                  </td>
                  <td className="px-4 py-2 text-right mono tabular-nums text-[var(--color-muted)]">
                    {num(v.metrics?.average_view_duration_seconds)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[var(--color-border)] px-4 py-2 mono text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
        {filtered.length} of {rows.length} videos
      </div>
    </div>
  );
}
