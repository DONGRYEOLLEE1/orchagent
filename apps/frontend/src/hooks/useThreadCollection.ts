/**
 * useThreadCollection — owns the sidebar thread list slice.
 *
 * Extracted from WorkspaceRouteRoot (Phase 3.2). Responsibility:
 *   - hold the {@link ThreadCollectionState} (threads + load state + error)
 *   - first-load fetch on mount
 *   - silent refresh after stream completion
 *   - optimistic insert / rename / pin / delete / patch helpers
 *
 * Out of scope (kept in caller during Phase 3.2):
 *   - cross-slice coordination (e.g. clearing the active thread when its
 *     summary is deleted). The hook exposes the raw setter through
 *     {@link UseThreadCollectionResult.setThreadCollection} so the caller can
 *     compose multi-slice transitions during the bridge period.
 *
 * The returned object shape is exported (`UseThreadCollectionResult`) so the
 * upcoming Phase 3.3 split can flow it through component props.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  deleteThread as deleteThreadApi,
  fetchThreads as fetchThreadsApi,
  patchThread as patchThreadApi,
} from '@/lib/api';
import {
  createInitialThreadCollectionState,
  patchThreadSummary,
  sortThreadSummaries,
  upsertThreadSummary,
} from '@/lib/workspace-state';
import type { ThreadCollectionState, ThreadSummary } from '@/types/thread';

export interface UseThreadCollectionResult {
  /** Current thread list slice. */
  threadCollection: ThreadCollectionState;
  /** Raw setter — exposed so cross-slice transitions can stay in the caller. */
  setThreadCollection: React.Dispatch<React.SetStateAction<ThreadCollectionState>>;
  /** Force a fetch of all threads from the API and replace the list. */
  loadThreads: () => Promise<void>;
  /** Silently refresh the list (e.g. after a stream completes). Errors bubble into state.error. */
  refreshThreadsSilently: () => Promise<ThreadSummary[] | null>;
  /** Insert (or move-to-top) a single thread summary in the local list. */
  addOptimisticThread: (summary: ThreadSummary) => void;
  /** Remove a thread from the local list without an API call (used for delete optimism). */
  removeThread: (threadId: string) => void;
  /** Partially patch a single thread summary in the local list. */
  patchThread: (threadId: string, patch: Partial<ThreadSummary>) => void;
  /** Optimistic rename + persist. Returns the server-updated summary or null on failure. */
  renameThread: (threadId: string, title: string) => Promise<ThreadSummary | null>;
  /** Optimistic pin toggle + persist. */
  togglePinnedThread: (threadId: string, pinned: boolean) => Promise<ThreadSummary | null>;
  /** Optimistic delete + persist. Returns true when the API call succeeded. */
  deleteThread: (threadId: string) => Promise<boolean>;
  /** Set the slice-level error message (e.g. cross-slice rehydration failure). */
  setError: (message: string) => void;
  /** Find a thread summary by id from the current slice. */
  findThread: (threadId: string) => ThreadSummary | undefined;
}

export function useThreadCollection(): UseThreadCollectionResult {
  const [threadCollection, setThreadCollection] = useState<ThreadCollectionState>(
    () => createInitialThreadCollectionState()
  );
  const threadsRef = useRef<ThreadSummary[]>(threadCollection.threads);

  useEffect(() => {
    threadsRef.current = threadCollection.threads;
  }, [threadCollection.threads]);

  const loadThreads = useCallback(async () => {
    setThreadCollection((prev) => ({
      ...prev,
      loadState: 'loading',
      error: '',
    }));

    try {
      const threads = await fetchThreadsApi();
      setThreadCollection({
        threads,
        loadState: 'success',
        error: '',
      });
    } catch (error) {
      setThreadCollection((prev) => ({
        ...prev,
        loadState: 'error',
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  }, []);

  // Auto-fire the initial load on mount, exactly like the caller used to do.
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setThreadCollection((prev) => ({
        ...prev,
        loadState: 'loading',
        error: '',
      }));
      try {
        const threads = await fetchThreadsApi();
        if (cancelled) {
          return;
        }
        setThreadCollection({
          threads,
          loadState: 'success',
          error: '',
        });
      } catch (error) {
        if (cancelled) {
          return;
        }
        setThreadCollection((prev) => ({
          ...prev,
          loadState: 'error',
          error: error instanceof Error ? error.message : 'Unknown error',
        }));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshThreadsSilently = useCallback(async () => {
    try {
      const threads = await fetchThreadsApi();
      setThreadCollection({
        threads,
        loadState: 'success',
        error: '',
      });
      return threads;
    } catch (error) {
      setThreadCollection((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      return null;
    }
  }, []);

  const addOptimisticThread = useCallback((summary: ThreadSummary) => {
    setThreadCollection((prev) => ({
      ...prev,
      threads: upsertThreadSummary(prev.threads, summary),
      error: '',
    }));
  }, []);

  const removeThread = useCallback((threadId: string) => {
    setThreadCollection((prev) => ({
      ...prev,
      threads: prev.threads.filter((thread) => thread.thread_id !== threadId),
      error: '',
    }));
  }, []);

  const patchThread = useCallback(
    (threadId: string, patch: Partial<ThreadSummary>) => {
      setThreadCollection((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, patch),
      }));
    },
    []
  );

  const renameThread = useCallback<
    UseThreadCollectionResult['renameThread']
  >(async (threadId, title) => {
    const existing = threadsRef.current.find((thread) => thread.thread_id === threadId);
    if (!existing) {
      return null;
    }

    setThreadCollection((prev) => ({
      ...prev,
      threads: patchThreadSummary(prev.threads, threadId, { title }),
    }));

    try {
      const updated = await patchThreadApi({ threadId, title });
      setThreadCollection((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, updated),
      }));
      return updated;
    } catch (error) {
      setThreadCollection((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, existing),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      return null;
    }
  }, []);

  const togglePinnedThread = useCallback<
    UseThreadCollectionResult['togglePinnedThread']
  >(async (threadId, pinned) => {
    const existing = threadsRef.current.find((thread) => thread.thread_id === threadId);
    if (!existing) {
      return null;
    }

    setThreadCollection((prev) => ({
      ...prev,
      threads: patchThreadSummary(prev.threads, threadId, { pinned }),
    }));

    try {
      const updated = await patchThreadApi({ threadId, pinned });
      setThreadCollection((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, updated),
      }));
      return updated;
    } catch (error) {
      setThreadCollection((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, existing),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      return null;
    }
  }, []);

  const deleteThread = useCallback<UseThreadCollectionResult['deleteThread']>(
    async (threadId) => {
      const existing = threadsRef.current.find((thread) => thread.thread_id === threadId);
      if (!existing) {
        return false;
      }

      const beforeDelete = threadsRef.current;

      setThreadCollection((prev) => ({
        ...prev,
        threads: prev.threads.filter((thread) => thread.thread_id !== threadId),
        error: '',
      }));

      try {
        await deleteThreadApi(threadId);
        return true;
      } catch (error) {
        const restored = sortThreadSummaries(
          beforeDelete.some((thread) => thread.thread_id === threadId)
            ? beforeDelete
            : [...beforeDelete, existing]
        );
        setThreadCollection((prev) => ({
          ...prev,
          threads: restored,
          error: error instanceof Error ? error.message : 'Unknown error',
        }));
        return false;
      }
    },
    []
  );

  const setError = useCallback((message: string) => {
    setThreadCollection((prev) => ({
      ...prev,
      error: message,
    }));
  }, []);

  const findThread = useCallback((threadId: string) => {
    return threadsRef.current.find((thread) => thread.thread_id === threadId);
  }, []);

  return {
    threadCollection,
    setThreadCollection,
    loadThreads,
    refreshThreadsSilently,
    addOptimisticThread,
    removeThread,
    patchThread,
    renameThread,
    togglePinnedThread,
    deleteThread,
    setError,
    findThread,
  };
}
