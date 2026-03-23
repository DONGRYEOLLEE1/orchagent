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
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-slate-800/70 bg-slate-900/30">
      <div className="border-b border-slate-800/70 px-4 py-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
            <MessageSquareText size={16} className="text-blue-400" />
            <span>Threads</span>
          </div>

          <button
            type="button"
            onClick={onNewChat}
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-300 transition-colors hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-900 disabled:text-slate-600"
          >
            <Plus size={14} />
            <span>New Chat</span>
          </button>
        </div>

        <p className="text-xs leading-5 text-slate-500">
          Recent sessions live here. Pick a thread to restore it or start a fresh draft.
        </p>

        {error ? (
          <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            {error}
          </div>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {loadState === 'loading' && threads.length === 0 ? (
          <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-800 bg-black/10 text-slate-500">
            <Loader2 size={18} className="animate-spin text-blue-400" />
            <span className="text-xs uppercase tracking-[0.18em]">Loading threads</span>
          </div>
        ) : null}

        {loadState !== 'loading' && threads.length === 0 ? (
          <div className="flex h-full min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-800 bg-black/10 px-6 text-center">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-3 text-slate-400">
              <MessageSquareText size={20} />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-300">No saved threads yet</div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Start a new chat and this panel will become your session archive.
              </p>
            </div>
          </div>
        ) : null}

        {threads.length > 0 ? (
          <div className="space-y-3">
            {threads.map((thread) => (
              <ThreadListItem
                key={thread.thread_id}
                thread={thread}
                selected={selectedThreadId === thread.thread_id}
                disabled={disabled}
                onSelect={onSelectThread}
                onRename={onRenameThread}
                onTogglePinned={onTogglePinnedThread}
              />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
