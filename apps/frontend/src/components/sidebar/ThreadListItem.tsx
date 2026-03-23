import { Clock3, Edit3, MessageSquareText, Pin, PinOff, Trash2 } from 'lucide-react';

import React, { useState } from 'react';

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
  onRename,
  onTogglePinned,
  onDelete,
}: {
  thread: ThreadSummary;
  selected: boolean;
  disabled: boolean;
  onSelect?: (threadId: string) => void;
  onRename?: (threadId: string, title: string) => void | Promise<void>;
  onTogglePinned?: (threadId: string, pinned: boolean) => void | Promise<void>;
  onDelete?: (threadId: string) => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState(thread.title);

  const submitRename = async () => {
    const normalized = draftTitle.trim();
    if (!normalized || normalized === thread.title) {
      setEditing(false);
      setDraftTitle(thread.title);
      return;
    }

    setEditing(false);
    await onRename?.(thread.thread_id, normalized);
  };

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

  return (
    <div
      className={baseClassName}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive && !disabled ? 0 : undefined}
      aria-label={interactive ? `Open thread ${thread.title}` : undefined}
      aria-disabled={interactive && disabled ? 'true' : undefined}
      onClick={
        interactive && !disabled
          ? () => onSelect?.(thread.thread_id)
          : undefined
      }
      onKeyDown={
        interactive && !disabled
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect?.(thread.thread_id);
              }
            }
          : undefined
      }
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          {editing ? (
            <input
              aria-label={`Rename thread ${thread.thread_id}`}
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              onBlur={() => void submitRename()}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void submitRename();
                }
                if (e.key === 'Escape') {
                  setDraftTitle(thread.title);
                  setEditing(false);
                }
              }}
              autoFocus
              className="w-full rounded-lg border border-blue-500/40 bg-slate-950/80 px-2 py-1 text-sm font-semibold text-slate-100 outline-none"
              disabled={disabled}
            />
          ) : (
            <div className="truncate text-sm font-semibold text-slate-100">
              {thread.title}
            </div>
          )}
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">
            {thread.preview || 'No preview available yet.'}
          </div>
        </div>

        <div className="mt-0.5 flex shrink-0 items-center gap-2">
          {thread.pinned ? (
            <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-200">
              Pinned
            </span>
          ) : null}
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
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setDraftTitle(thread.title);
              setEditing(true);
            }}
            disabled={disabled || !onRename}
            aria-label={`Rename ${thread.title}`}
            className="rounded-lg border border-slate-800 bg-black/20 p-1.5 text-slate-500 transition hover:border-slate-700 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Edit3 size={12} />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void onTogglePinned?.(thread.thread_id, !thread.pinned);
            }}
            disabled={disabled || !onTogglePinned}
            aria-label={thread.pinned ? `Unpin ${thread.title}` : `Pin ${thread.title}`}
            className="rounded-lg border border-slate-800 bg-black/20 p-1.5 text-slate-500 transition hover:border-slate-700 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {thread.pinned ? <PinOff size={12} /> : <Pin size={12} />}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void onDelete?.(thread.thread_id);
            }}
            disabled={disabled || !onDelete}
            aria-label={`Delete ${thread.title}`}
            className="rounded-lg border border-slate-800 bg-black/20 p-1.5 text-slate-500 transition hover:border-red-500/40 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 size={12} />
          </button>
          <span className="inline-flex items-center gap-1.5 uppercase tracking-[0.18em]">
            <MessageSquareText size={12} className="shrink-0" />
            <span>{thread.latest_status || 'saved'}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
