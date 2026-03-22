import { Activity, Hash, Layers3 } from 'lucide-react';

import type { ThreadLoadState } from '@/types/thread';

function formatStatus(value: string | null): string {
  if (!value) {
    return 'Draft';
  }

  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatLastActivity(value: string | null): string {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '-';
  }

  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function StatusRow({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className={valueClassName}>{value}</span>
    </div>
  );
}

export function SessionStatusCard({
  loading,
  checkpointId,
  activeThreadId,
  threadCount,
  threadLoadState,
  latestStatus,
  lastActivityAt,
  historicalView,
}: {
  loading: boolean;
  checkpointId: string;
  activeThreadId: string;
  threadCount: number;
  threadLoadState: ThreadLoadState;
  latestStatus: string | null;
  lastActivityAt: string | null;
  historicalView: boolean;
}) {
  return (
    <section className="rounded-2xl border border-slate-800/70 bg-slate-900/30 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
        <Activity size={16} className="text-cyan-400" />
        <span>Session State</span>
      </div>

      <div className="space-y-2.5">
        <StatusRow
          label="Engine"
          value={loading ? 'Active' : 'Idle'}
          valueClassName={
            loading
              ? 'font-medium text-blue-400'
              : 'font-medium text-emerald-400'
          }
        />

        <StatusRow
          label="Status"
          value={formatStatus(latestStatus)}
          valueClassName="font-medium text-slate-300"
        />

        <StatusRow
          label="Last Active"
          value={formatLastActivity(lastActivityAt)}
          valueClassName="font-mono text-xs text-slate-500"
        />

        <StatusRow
          label="Checkpoint"
          value={checkpointId || '-'}
          valueClassName="max-w-[12rem] truncate font-mono text-xs text-slate-500"
        />

        <StatusRow
          label="Threads"
          value={threadLoadState === 'loading' ? '...' : String(threadCount)}
          valueClassName="font-mono text-xs text-slate-500"
        />

        <div className="rounded-xl border border-slate-800/60 bg-black/10 px-3 py-2.5">
          <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            <Layers3 size={12} />
            <span>{historicalView ? 'History Snapshot' : 'Current Thread'}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <Hash size={12} className="shrink-0 text-slate-500" />
            <span className="truncate font-mono text-[11px] text-slate-400">
              {activeThreadId || 'draft_session'}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
