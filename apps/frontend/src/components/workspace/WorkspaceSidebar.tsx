"use client";

import React from 'react';
import { X } from 'lucide-react';

import { ThreadListSidebar } from '@/components/sidebar/ThreadListSidebar';
import type { ThreadSummary, ThreadLoadState } from '@/types/thread';

export interface WorkspaceSidebarProps {
  /** Persisted thread summaries to render in the list. */
  threads: ThreadSummary[];
  /** Load state for the thread collection (drives skeletons / errors). */
  loadState: ThreadLoadState;
  /** Latest thread-collection error string, if any. */
  error: string;
  /** Active thread id (visually highlighted). */
  activeThreadId: string;
  /** Disable selection/new-chat while a stream or HITL is in-flight. */
  disabled: boolean;
  /** Mobile drawer open state (controlled by parent). */
  mobileSidebarOpen: boolean;
  /** Close the mobile drawer. */
  onCloseMobileSidebar: () => void;
  /** New Chat handler. */
  onCreateThread: () => void;
  /** Select an existing thread. */
  onSelectThread: (threadId: string) => void;
  /** Rename a thread. */
  onRenameThread: (threadId: string, title: string) => void | Promise<void>;
  /** Toggle pinned flag on a thread. */
  onTogglePinnedThread: (threadId: string, pinned: boolean) => void | Promise<void>;
  /** Delete a thread. */
  onDeleteThread: (threadId: string) => void | Promise<void>;
}

/**
 * Sidebar composition for the workspace route: desktop rail + mobile drawer.
 * Owns no state — receives drawer open/close from parent so other layout
 * regions (top nav, composer) can also drive the same toggle.
 */
export function WorkspaceSidebar({
  threads,
  loadState,
  error,
  activeThreadId,
  disabled,
  mobileSidebarOpen,
  onCloseMobileSidebar,
  onCreateThread,
  onSelectThread,
  onRenameThread,
  onTogglePinnedThread,
  onDeleteThread,
}: WorkspaceSidebarProps) {
  const sidebarContent = (
    <ThreadListSidebar
      threads={threads}
      loadState={loadState}
      error={error}
      selectedThreadId={activeThreadId}
      disabled={disabled}
      onNewChat={onCreateThread}
      onSelectThread={onSelectThread}
      onRenameThread={onRenameThread}
      onTogglePinnedThread={onTogglePinnedThread}
      onDeleteThread={onDeleteThread}
    />
  );

  return (
    <>
      <aside className="hidden h-full w-64 shrink-0 border-r border-[rgba(255,255,255,0.05)] bg-[rgba(17,19,26,0.96)] py-6 lg:flex lg:flex-col">
        {sidebarContent}
      </aside>

      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden">
          <button
            type="button"
            aria-label="Close thread sidebar"
            onClick={onCloseMobileSidebar}
            className="absolute inset-0 bg-[rgba(7,9,13,0.78)] backdrop-blur-sm"
          />

          <div className="absolute inset-y-0 left-0 flex w-[min(24rem,92vw)] flex-col border-r border-[rgba(255,255,255,0.06)] bg-[rgba(17,19,26,0.98)] py-6 shadow-2xl shadow-black/50">
            <div className="mb-4 flex items-center justify-between px-6">
              <div>
                <div className="font-[var(--font-display)] text-[20px] font-bold text-[#00f0ff]">
                  OrchAgent
                </div>
                <div className="text-[10px] uppercase tracking-[0.22em] text-[rgba(170,170,179,0.7)]">
                  Chat Workspace
                </div>
              </div>
              <button
                type="button"
                onClick={onCloseMobileSidebar}
                className="rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.4)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0]"
              >
                <X size={16} />
              </button>
            </div>
            {sidebarContent}
          </div>
        </div>
      ) : null}
    </>
  );
}

export default WorkspaceSidebar;
