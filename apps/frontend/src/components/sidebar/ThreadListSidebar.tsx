import { Loader2, MessageSquareText, Plus } from 'lucide-react';

import { ThreadListItem } from '@/components/sidebar/ThreadListItem';
import type { ThreadLoadState, ThreadSummary } from '@/types/thread';

export function ThreadListSidebar({
  threads,
  loadState,
  error,
  selectedThreadId,
  disabled,
  onNewChat,
  onSelectThread,
  onRenameThread,
  onTogglePinnedThread,
  onDeleteThread,
}: {
  threads: ThreadSummary[];
  loadState: ThreadLoadState;
  error: string;
  selectedThreadId: string;
  disabled: boolean;
  onNewChat: () => void;
  onSelectThread?: (threadId: string) => void;
  onRenameThread?: (threadId: string, title: string) => void | Promise<void>;
  onTogglePinnedThread?: (threadId: string, pinned: boolean) => void | Promise<void>;
  onDeleteThread?: (threadId: string) => void | Promise<void>;
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="px-6 pb-6 pt-2">
        <div className="mb-1 flex items-center gap-2 text-[18px] font-bold text-[#e7e7f0]">
          <span className="font-[var(--font-display)]">Threads</span>
        </div>
        <p className="mb-5 text-[12px] text-[rgba(170,170,179,0.68)]">
          AI Orchestration History
        </p>

        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
          <MessageSquareText size={16} className="text-[#8ff5ff]" />
          <span className="text-[12px] uppercase tracking-[0.18em] text-[rgba(170,170,179,0.7)]">
            Active Threads
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onNewChat}
            disabled={disabled}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[12px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-4 py-3 text-[12px] font-bold text-[#005359] shadow-[0px_10px_15px_-3px_rgba(143,245,255,0.12),0px_4px_6px_-4px_rgba(143,245,255,0.12)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:bg-slate-900 disabled:text-slate-600"
          >
            <Plus size={14} />
            <span>New Chat</span>
          </button>
        </div>

        {error ? (
          <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            {error}
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
        {loadState === 'loading' && threads.length === 0 ? (
          <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-[12px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.28)] text-[rgba(170,170,179,0.78)]">
            <Loader2 size={18} className="animate-spin text-[#8ff5ff]" />
            <span className="text-xs uppercase tracking-[0.18em]">Loading threads</span>
          </div>
        ) : null}

        {loadState !== 'loading' && threads.length === 0 ? (
          <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-[12px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.28)] px-6 text-center">
            <div className="rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.42)] p-3 text-[rgba(170,170,179,0.85)]">
              <MessageSquareText size={20} />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#e7e7f0]">No saved threads yet</div>
              <p className="mt-1 text-xs leading-5 text-[rgba(170,170,179,0.72)]">
                Start a new chat and this panel will become your session archive.
              </p>
            </div>
          </div>
        ) : null}

        {threads.length > 0 ? (
          <div className="space-y-2">
            {threads.map((thread) => (
              <ThreadListItem
                key={thread.thread_id}
                thread={thread}
                selected={selectedThreadId === thread.thread_id}
                disabled={disabled}
                onSelect={onSelectThread}
                onRename={onRenameThread}
                onTogglePinned={onTogglePinnedThread}
                onDelete={onDeleteThread}
              />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
