import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/config";
import { NotConfigured } from "@/components/NotConfigured";
import { Panel, EmptyState } from "@/components/ui";
import { ChannelCard } from "@/components/channels/ChannelCard";
import { ChannelComparison } from "@/components/channels/ChannelComparison";
import { getChannelContext } from "@/lib/channels-server";
import { channelHealth, channelStats } from "@/lib/channels";
import { getDictionary } from "@/lib/i18n/server";
import type {
  ContentQueueRow,
  MetricsSnapshotRow,
  SystemEventRow,
  VideoRow,
} from "@/lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * Channel management: every channel, its configuration, its credential status
 * and its own health — plus the cross-channel comparison.
 *
 * Deliberately NOT scoped by the header switcher: this is the page where you
 * look at all of them side by side.
 */
export default async function ChannelsPage() {
  if (!isSupabaseConfigured) return <NotConfigured />;
  const { t } = await getDictionary();

  const { channels, credentials, notMigrated } = await getChannelContext();
  const supabase = await createClient();

  let events: SystemEventRow[] = [];
  let videos: VideoRow[] = [];
  let snapshots: MetricsSnapshotRow[] = [];
  let queue: ContentQueueRow[] = [];

  if (supabase) {
    const [ev, vid, snap, q] = await Promise.all([
      supabase.from("system_events").select("*").order("ts", { ascending: false }).limit(500),
      supabase.from("videos").select("*").order("published_at", { ascending: false }).limit(500),
      supabase.from("metrics_snapshots").select("*").order("snapshot_date", { ascending: false }).limit(500),
      supabase.from("content_queue").select("*").limit(500),
    ]);
    events = (ev.data as SystemEventRow[]) ?? [];
    videos = (vid.data as VideoRow[]) ?? [];
    snapshots = (snap.data as MetricsSnapshotRow[]) ?? [];
    queue = (q.data as ContentQueueRow[]) ?? [];
  }

  const stats = channelStats(channels, videos, snapshots);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">{t.channels.title}</h1>
          <p className="mono text-[11px] text-[var(--color-muted)]">{t.channels.subtitle}</p>
        </div>
        {!notMigrated && (
          <Link
            href="/channels/new"
            className="press rounded-md border border-[var(--color-primary-dim)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[var(--color-primary)] hover:bg-[var(--color-panel-2)]"
          >
            + {t.channels.add}
          </Link>
        )}
      </div>

      {notMigrated ? (
        <Panel title={t.channels.title}>
          <EmptyState>{t.channels.notMigrated}</EmptyState>
        </Panel>
      ) : channels.length === 0 ? (
        <Panel title={t.channels.title}>
          <EmptyState>{t.channels.empty}</EmptyState>
        </Panel>
      ) : (
        <>
          <Panel title={t.channels.compare}>
            <ChannelComparison stats={stats} />
          </Panel>

          <p className="text-[11px] leading-relaxed text-[var(--color-muted)]">
            {t.channels.isolationNote}
          </p>

          <div className="grid gap-3 lg:grid-cols-2">
            {channels.map((channel) => (
              <ChannelCard
                key={channel.channel_id}
                channel={channel}
                credential={credentials.find(
                  (c) => c.channel_id === channel.channel_id && c.provider === "youtube",
                )}
                health={channelHealth(
                  channel,
                  events,
                  credentials.find((c) => c.channel_id === channel.channel_id),
                )}
                queued={
                  queue.filter((q) => q.channel_id === channel.channel_id && q.status === "queued").length
                }
                videos={videos.filter((v) => v.channel_id === channel.channel_id).length}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
