/**
 * useStreamSession — owns the live SSE stream session slice.
 *
 * Extracted from WorkspaceRouteRoot (Phase 3.2). Responsibility:
 *   - hold the {@link StreamSessionState} (loading / currentNode / history /
 *     streamError / isInterrupted)
 *   - expose lifecycle helpers: startStream / completeStream / cancelStream /
 *     failStream / markInterrupted
 *
 * The hook intentionally does NOT call into `sendChatStream` or
 * `resumeChatStream`. Those calls remain in the caller because they need to
 * coordinate with `useActiveThread`, `useThreadCollection`,
 * `useActionSpace`, and the combined SSE reducer ref. The hook only owns the
 * "session status" slice; the caller drives the lifecycle by calling the
 * action functions returned here.
 *
 * The returned object shape is exported so the upcoming Phase 3.3 split can
 * pass it into a dedicated `StreamConsumer` / HITL `Panel` component.
 */
import { useCallback, useState } from 'react';

import {
  createHistoricalStreamSessionState,
  createInitialStreamSessionState,
} from '@/lib/workspace-state';
import type { StreamSessionState } from '@/types/thread';

export interface UseStreamSessionResult {
  /** Current stream session slice. */
  streamSession: StreamSessionState;
  /** Raw setter — exposed so the SSE reducer can fan out per-slice patches. */
  setStreamSession: React.Dispatch<React.SetStateAction<StreamSessionState>>;
  /** Reset back to the initial idle state. */
  resetSession: () => void;
  /** Rehydrate the slice for a historical thread (already-completed status). */
  hydrateHistorical: (latestStatus: string | null) => void;
  /**
   * Mark the session as starting. Sets `loading=true` and clears prior history
   * + errors. Used by the caller right before calling `sendChatStream`.
   */
  startStream: () => void;
  /**
   * Mark the session as resuming after a HITL interrupt. Same as startStream
   * but preserves history and explicitly sets `currentNode='Resuming...'`.
   */
  startResume: () => void;
  /** Mark the session as no longer loading without changing anything else. */
  completeStream: () => void;
  /** Cancel an in-flight stream by clearing `loading` and any error. */
  cancelStream: () => void;
  /**
   * Mark the session as errored. Sets `loading=false`, `currentNode='Errored'`
   * and stores the error message.
   */
  failStream: (errorMessage: string) => void;
  /**
   * Restore the session to its interrupted-but-resumable state. Used when a
   * resume call fails before any SSE event arrives.
   */
  markInterrupted: (currentNode?: string) => void;
}

export function useStreamSession(): UseStreamSessionResult {
  const [streamSession, setStreamSession] = useState<StreamSessionState>(
    () => createInitialStreamSessionState()
  );

  const resetSession = useCallback(() => {
    setStreamSession(createInitialStreamSessionState());
  }, []);

  const hydrateHistorical = useCallback((latestStatus: string | null) => {
    setStreamSession(createHistoricalStreamSessionState(latestStatus));
  }, []);

  const startStream = useCallback(() => {
    setStreamSession({
      ...createInitialStreamSessionState(),
      loading: true,
    });
  }, []);

  const startResume = useCallback(() => {
    setStreamSession((prev) => ({
      ...prev,
      isInterrupted: false,
      loading: true,
      currentNode: 'Resuming...',
      streamError: '',
    }));
  }, []);

  const completeStream = useCallback(() => {
    setStreamSession((prev) => ({
      ...prev,
      loading: false,
    }));
  }, []);

  const cancelStream = useCallback(() => {
    setStreamSession((prev) => ({
      ...prev,
      loading: false,
      streamError: '',
    }));
  }, []);

  const failStream = useCallback((errorMessage: string) => {
    setStreamSession((prev) => ({
      ...prev,
      loading: false,
      currentNode: 'Errored',
      streamError: errorMessage,
    }));
  }, []);

  const markInterrupted = useCallback((currentNode = 'Requires User Action') => {
    setStreamSession((prev) => ({
      ...prev,
      loading: false,
      isInterrupted: true,
      currentNode,
    }));
  }, []);

  return {
    streamSession,
    setStreamSession,
    resetSession,
    hydrateHistorical,
    startStream,
    startResume,
    completeStream,
    cancelStream,
    failStream,
    markInterrupted,
  };
}
