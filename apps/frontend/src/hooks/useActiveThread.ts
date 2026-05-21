/**
 * useActiveThread — owns the active thread slice.
 *
 * Extracted from WorkspaceRouteRoot (Phase 3.2). Responsibility:
 *   - hold the {@link ActiveThreadState} (currently focused thread)
 *   - load thread detail (messages + repo binding + coding summary)
 *   - append messages / patch view mode / clear on new chat
 *
 * Network calls live here so the caller no longer threads `fetchThreadDetail`
 * through its own try/catch. Cross-slice coordination (sidebar list refresh,
 * router navigation, telemetry hydration) stays in the caller, which is why
 * the raw setter is also returned.
 *
 * The returned object shape is exported so the upcoming Phase 3.3 split can
 * pass it directly into a `MessageThreadView` / `Composer` component.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchThreadDetail as fetchThreadDetailApi } from '@/lib/api';
import { appendAssistantText } from '@/lib/chat-stream';
import {
  applyThreadSummaryToActiveThread,
  createActiveThreadStateFromDetail,
  createInitialActiveThreadState,
} from '@/lib/workspace-state';
import type { ChatMessage } from '@/types/agent';
import type {
  ActiveThreadState,
  RepositoryBinding,
  ThreadDetail,
  ThreadSummary,
} from '@/types/thread';

export interface UseActiveThreadResult {
  /** Current active thread slice. */
  activeThread: ActiveThreadState;
  /** Raw setter — exposed so cross-slice transitions can stay in the caller. */
  setActiveThread: React.Dispatch<React.SetStateAction<ActiveThreadState>>;
  /** Latest active threadId mirrored via ref. Stable across renders. */
  activeThreadIdRef: React.MutableRefObject<string>;
  /**
   * Fetch a thread's full detail and hydrate the slice with it. Returns the
   * detail on success so the caller can chain telemetry hydration / sidebar
   * upsert in the same async flow. Throws on API failure.
   */
  loadThread: (threadId: string) => Promise<ThreadDetail>;
  /** Reset the slice back to the empty-draft state and clear the activeThreadIdRef. */
  clearActiveThread: () => void;
  /** Mark the slice as loading the given threadId (used while route fetch is in flight). */
  beginLoadingThread: (threadId: string) => void;
  /** Append a chat message (e.g. optimistic user message) to the slice. */
  appendMessage: (message: ChatMessage) => void;
  /**
   * Append text to an assistant bubble identified by `assistantId`. If the last
   * message is the same bubble the text is concatenated, otherwise a new
   * assistant message is created. Mirrors {@link appendAssistantText}.
   */
  appendAssistantTextChunk: (assistantId: string, text: string) => void;
  /** Replace the messages array (used to clear or restore historical state). */
  setMessages: (messages: ChatMessage[]) => void;
  /** Patch the repository binding without rewriting the whole slice. */
  setRepoBinding: (binding: RepositoryBinding | null) => void;
  /**
   * Apply an incoming thread summary (e.g. from a silent refresh) to the active
   * slice — keeps it in sync with the sidebar without overwriting unrelated
   * fields. No-op if `summary.thread_id` does not match the active thread.
   */
  applySummary: (summary: ThreadSummary) => void;
}

export function useActiveThread(): UseActiveThreadResult {
  const [activeThread, setActiveThread] = useState<ActiveThreadState>(
    () => createInitialActiveThreadState()
  );
  const activeThreadIdRef = useRef<string>('');

  useEffect(() => {
    activeThreadIdRef.current = activeThread.threadId;
  }, [activeThread.threadId]);

  const loadThread = useCallback(async (threadId: string) => {
    const detail = await fetchThreadDetailApi(threadId);
    activeThreadIdRef.current = threadId;
    setActiveThread(createActiveThreadStateFromDetail(detail));
    return detail;
  }, []);

  const clearActiveThread = useCallback(() => {
    activeThreadIdRef.current = '';
    setActiveThread(createInitialActiveThreadState());
  }, []);

  const beginLoadingThread = useCallback((threadId: string) => {
    activeThreadIdRef.current = threadId;
    setActiveThread({
      ...createInitialActiveThreadState(),
      threadId,
      detailLoadState: 'loading',
    });
  }, []);

  const appendMessage = useCallback((message: ChatMessage) => {
    setActiveThread((prev) => ({
      ...prev,
      messages: [...prev.messages, message],
    }));
  }, []);

  const appendAssistantTextChunk = useCallback(
    (assistantId: string, text: string) => {
      setActiveThread((prev) => ({
        ...prev,
        messages: appendAssistantText(prev.messages, assistantId, text),
      }));
    },
    []
  );

  const setMessages = useCallback((messages: ChatMessage[]) => {
    setActiveThread((prev) => ({
      ...prev,
      messages,
    }));
  }, []);

  const setRepoBinding = useCallback((binding: RepositoryBinding | null) => {
    setActiveThread((prev) => ({
      ...prev,
      repoBinding: binding,
    }));
  }, []);

  const applySummary = useCallback((summary: ThreadSummary) => {
    setActiveThread((prev) => {
      if (prev.threadId !== summary.thread_id) {
        return prev;
      }
      return applyThreadSummaryToActiveThread(prev, summary);
    });
  }, []);

  return {
    activeThread,
    setActiveThread,
    activeThreadIdRef,
    loadThread,
    clearActiveThread,
    beginLoadingThread,
    appendMessage,
    appendAssistantTextChunk,
    setMessages,
    setRepoBinding,
    applySummary,
  };
}
