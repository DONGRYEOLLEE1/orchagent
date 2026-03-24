import { Edit3, MoreHorizontal, Pin, PinOff, Trash2 } from 'lucide-react';

import React, { useState } from 'react';

import type { ThreadSummary } from '@/types/thread';

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
  const [menuOpen, setMenuOpen] = useState(false);

  const submitRename = async () => {
    const normalized = draftTitle.trim();
    if (!normalized || normalized === thread.title) {
      setEditing(false);
      setDraftTitle(thread.title);
      return;
    }

    setEditing(false);
    setMenuOpen(false);
    await onRename?.(thread.thread_id, normalized);
  };

  const interactive = Boolean(onSelect);
  const hasActions = Boolean(onRename || onTogglePinned || onDelete);
  const baseClassName = [
    'group relative w-full rounded-[10px] px-3.5 py-2.5 text-left transition-all duration-200',
    selected
      ? 'bg-[rgba(29,31,40,0.9)] shadow-[inset_2px_0_0_0_rgba(172,137,255,0.65)]'
      : 'bg-transparent hover:bg-[rgba(29,31,40,0.44)]',
    interactive && !disabled ? 'cursor-pointer' : '',
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
          ? () => {
              setMenuOpen(false);
              onSelect?.(thread.thread_id);
            }
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
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
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
            <div className="line-clamp-2 text-[13px] font-semibold leading-[1.35rem] text-[#e7e7f0]">
              {thread.title}
            </div>
          )}

          {thread.pinned ? (
            <span className="mt-1.5 inline-flex rounded-full border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.16em] text-amber-200">
              Pinned
            </span>
          ) : null}
        </div>

        {hasActions ? (
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((prev) => !prev);
              }}
              disabled={disabled}
              aria-label={`Thread actions ${thread.title}`}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className={[
                'rounded-[8px] bg-transparent p-1 text-[rgba(170,170,179,0.74)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]',
                menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
                disabled ? 'cursor-not-allowed opacity-50' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <MoreHorizontal size={14} />
            </button>

            {menuOpen ? (
              <div
                role="menu"
                className="absolute right-0 top-10 z-10 flex min-w-40 flex-col rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(12,14,20,0.96)] p-1.5 shadow-2xl shadow-black/40 backdrop-blur-xl"
                onClick={(e) => e.stopPropagation()}
              >
                {onRename ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDraftTitle(thread.title);
                      setEditing(true);
                      setMenuOpen(false);
                    }}
                    disabled={disabled}
                    aria-label={`Rename ${thread.title}`}
                    className="inline-flex items-center gap-2 rounded-[10px] px-2.5 py-2 text-left text-xs text-[#e7e7f0] transition hover:bg-[rgba(35,38,46,0.8)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Edit3 size={12} />
                    <span>스레드명 수정</span>
                  </button>
                ) : null}

                {onTogglePinned ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      void onTogglePinned?.(thread.thread_id, !thread.pinned);
                    }}
                    disabled={disabled}
                    aria-label={thread.pinned ? `Unpin ${thread.title}` : `Pin ${thread.title}`}
                    className="inline-flex items-center gap-2 rounded-[10px] px-2.5 py-2 text-left text-xs text-[#e7e7f0] transition hover:bg-[rgba(35,38,46,0.8)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {thread.pinned ? <PinOff size={12} /> : <Pin size={12} />}
                    <span>{thread.pinned ? '핀 해제' : '핀'}</span>
                  </button>
                ) : null}

                {onDelete ? (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      void onDelete?.(thread.thread_id);
                    }}
                    disabled={disabled}
                    aria-label={`Delete ${thread.title}`}
                    className="inline-flex items-center gap-2 rounded-[10px] px-2.5 py-2 text-left text-xs text-red-200 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash2 size={12} />
                    <span>삭제</span>
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
