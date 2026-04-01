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
              <>
                <button
                  type="button"
                  aria-label={`Close thread actions menu for ${thread.title}`}
                  className="fixed inset-0 z-[5] cursor-default bg-transparent"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(false);
                  }}
                />
                <div
                  role="menu"
                  className="absolute right-[-10px] top-[calc(100%+10px)] z-10 flex w-[198px] flex-col rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(44,45,49,0.98)] p-2 shadow-[0_22px_60px_rgba(0,0,0,0.48)] backdrop-blur-xl"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex flex-col gap-0.5">
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
                        className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2.5 text-left font-[var(--font-body)] text-[13px] font-semibold leading-[1.35rem] text-[#f1f3f7] transition hover:bg-[rgba(255,255,255,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Edit3 size={14} strokeWidth={1.9} />
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
                        className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2.5 text-left font-[var(--font-body)] text-[13px] font-semibold leading-[1.35rem] text-[#f1f3f7] transition hover:bg-[rgba(255,255,255,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {thread.pinned ? <PinOff size={14} strokeWidth={1.9} /> : <Pin size={14} strokeWidth={1.9} />}
                        <span>{thread.pinned ? '핀 해제' : '핀'}</span>
                      </button>
                    ) : null}
                  </div>

                  {onDelete ? (
                    <div className="mt-2 border-t border-[rgba(255,255,255,0.1)] pt-2">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpen(false);
                          void onDelete?.(thread.thread_id);
                        }}
                        disabled={disabled}
                        aria-label={`Delete ${thread.title}`}
                        className="inline-flex w-full items-center gap-2 rounded-[12px] px-3 py-2.5 text-left font-[var(--font-body)] text-[13px] font-semibold leading-[1.35rem] text-[#ff6b6b] transition hover:bg-[rgba(255,107,107,0.1)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Trash2 size={14} strokeWidth={1.9} />
                        <span>삭제</span>
                      </button>
                    </div>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
