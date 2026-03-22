import { Clock3, MessageSquareText } from 'lucide-react';

import type { ThreadSummary } from '@/types/thread';

function formatLastActivity(value: string | null): string {
  if (!value) {
    return 'No activity';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Recent';
  }

  const now = new Date();
  const sameDay = now.toDateString() === date.toDateString();

  if (sameDay) {
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }

  if (now.getFullYear() === date.getFullYear()) {
    return date.toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
    });
  }

  return date.toLocaleDateString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function statusTone(status: string | null): string {
  if (status === 'completed') {
    return 'bg-emerald-400';
  }
  if (status === 'interrupted') {
    return 'bg-amber-400';
  }
  if (status === 'errored') {
    return 'bg-red-400';
  }
  if (status === 'running') {
    return 'bg-blue-400';
  }

  return 'bg-slate-600';
}

export function ThreadListItem({
  thread,
  selected,
  disabled,
  onSelect,
}: {
  thread: ThreadSummary;
  selected: boolean;
  disabled: boolean;
  onSelect?: (threadId: string) => void;
}) {
  const interactive = Boolean(onSelect);
  const baseClassName = [
    'w-full rounded-2xl border p-3 text-left transition-all duration-200',
    selected
      ? 'border-blue-500/50 bg-blue-500/10 shadow-[0_0_20px_rgba(59,130,246,0.12)]'
      : 'border-slate-800/70 bg-slate-900/30 hover:border-slate-700 hover:bg-slate-900/50',
    disabled ? 'cursor-not-allowed opacity-80' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const content = (
    <>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-100">
            {thread.title}
          </div>
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">
            {thread.preview || 'No preview available yet.'}
          </div>
        </div>

        <div className="mt-0.5 flex shrink-0 items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${statusTone(thread.latest_status)}`} />
          <span className="rounded-full border border-slate-700/80 bg-black/20 px-2 py-0.5 text-[10px] font-medium text-slate-500">
            {thread.message_count}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 size={12} className="shrink-0" />
          <span>{formatLastActivity(thread.last_activity_at)}</span>
        </span>
        <span className="inline-flex items-center gap-1.5 uppercase tracking-[0.18em]">
          <MessageSquareText size={12} className="shrink-0" />
          <span>{thread.latest_status || 'saved'}</span>
        </span>
      </div>
    </>
  );

  if (!interactive) {
    return <div className={baseClassName}>{content}</div>;
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onSelect?.(thread.thread_id)}
      aria-label={`Open thread ${thread.title}`}
      className={baseClassName}
    >
      {content}
    </button>
  );
}
