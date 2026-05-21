/**
 * useActionSpace — owns the right-side action space slice (Reasoning + Coding).
 *
 * Extracted from WorkspaceRouteRoot (Phase 3.2). Responsibility:
 *   - hold the {@link ActionSpaceState} (tool executions, reasoning entries,
 *     suggested queries, raw SSE traces, active right tab)
 *   - expose helpers to switch the active right tab, mark loading/error for
 *     the suggestions panel, and reset the slice on thread switch
 *
 * Out of scope (kept in caller during Phase 3.2):
 *   - the `lastAutoTabThreadRef` auto-switch effect that flips
 *     `activeRightTab` based on `repoBinding` + `hasCodingSignal`. That effect
 *     reads two other slices and is easier to keep co-located with the active
 *     thread slice. Moving it here would require passing both signals in via
 *     props, which is exactly the kind of work Phase 3.3 will tackle when the
 *     component split lands.
 *
 * The returned object shape is exported so the upcoming Phase 3.3 split can
 * pass it into the `RightAside` / `ReasoningPanel` components.
 */
import { useCallback, useState } from 'react';

import { createInitialActionSpaceState } from '@/lib/workspace-state';
import type { ActionSpaceState, ReasoningEntry, RightTab } from '@/types/thread';

export interface UseActionSpaceResult {
  /** Current action-space slice. */
  actionSpace: ActionSpaceState;
  /** Raw setter — exposed so the SSE reducer can fan out per-slice patches. */
  setActionSpace: React.Dispatch<React.SetStateAction<ActionSpaceState>>;
  /** Reset back to the initial empty state. Used on thread switch. */
  resetActionSpace: () => void;
  /**
   * Reset the slice while immediately marking the suggested-queries panel as
   * loading. Used right after the caller fires off a suggestions request so
   * the UI does not flash an empty state.
   */
  resetWithLoadingSuggestions: () => void;
  /** Switch which right-side tab is active (`reasoning` | `coding`). */
  setActiveRightTab: (tab: RightTab) => void;
  /** Replace the suggested queries list and flip the panel state to success/idle. */
  applySuggestedQueries: (queries: string[]) => void;
  /** Mark the suggested queries panel as loading. */
  beginSuggestedQueriesLoad: () => void;
  /** Mark the suggested queries panel as errored. */
  failSuggestedQueries: (message: string) => void;
  /**
   * Apply a historical telemetry payload (reasoning summary + suggested
   * queries) into the slice. Mirrors the inline updater the caller used.
   */
  applyHistoricalTelemetry: (params: {
    threadId: string;
    reasoningSummary: string;
    suggestedQueries: string[];
  }) => void;
  /**
   * Toggle the debug panel that shows raw SSE traces. The caller currently
   * does not expose a UI toggle for this; the setter exists for completeness
   * and to keep the slice fully addressable from the hook.
   */
  setShowDebug: (showDebug: boolean) => void;
}

export function useActionSpace(): UseActionSpaceResult {
  const [actionSpace, setActionSpace] = useState<ActionSpaceState>(
    () => createInitialActionSpaceState()
  );

  const resetActionSpace = useCallback(() => {
    setActionSpace(createInitialActionSpaceState());
  }, []);

  const resetWithLoadingSuggestions = useCallback(() => {
    setActionSpace({
      ...createInitialActionSpaceState(),
      suggestedQueriesState: 'loading',
    });
  }, []);

  const setActiveRightTab = useCallback((tab: RightTab) => {
    setActionSpace((prev) => ({
      ...prev,
      activeRightTab: tab,
    }));
  }, []);

  const applySuggestedQueries = useCallback((queries: string[]) => {
    setActionSpace((prev) => ({
      ...prev,
      suggestedQueries: queries,
      suggestedQueriesState: queries.length > 0 ? 'success' : 'idle',
      suggestedQueriesError: '',
    }));
  }, []);

  const beginSuggestedQueriesLoad = useCallback(() => {
    setActionSpace((prev) => ({
      ...prev,
      suggestedQueriesState: 'loading',
      suggestedQueriesError: '',
    }));
  }, []);

  const failSuggestedQueries = useCallback((message: string) => {
    setActionSpace((prev) => ({
      ...prev,
      suggestedQueriesState: 'error',
      suggestedQueriesError: message,
    }));
  }, []);

  const applyHistoricalTelemetry = useCallback<
    UseActionSpaceResult['applyHistoricalTelemetry']
  >(({ threadId, reasoningSummary, suggestedQueries }) => {
    setActionSpace((prev) => {
      const reasoningEntries: ReasoningEntry[] = reasoningSummary
        ? [
            {
              id: `historical:${threadId}`,
              displayName: 'Saved Summary',
              content: reasoningSummary,
            },
          ]
        : prev.reasoningEntries;

      return {
        ...prev,
        reasoning: reasoningSummary || prev.reasoning,
        reasoningEntries,
        suggestedQueries,
        suggestedQueriesState: suggestedQueries.length > 0 ? 'success' : 'idle',
        suggestedQueriesError: '',
      };
    });
  }, []);

  const setShowDebug = useCallback((showDebug: boolean) => {
    setActionSpace((prev) => ({
      ...prev,
      showDebug,
    }));
  }, []);

  return {
    actionSpace,
    setActionSpace,
    resetActionSpace,
    resetWithLoadingSuggestions,
    setActiveRightTab,
    applySuggestedQueries,
    beginSuggestedQueriesLoad,
    failSuggestedQueries,
    applyHistoricalTelemetry,
    setShowDebug,
  };
}
