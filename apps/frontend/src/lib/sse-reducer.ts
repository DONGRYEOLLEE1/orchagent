/**
 * Pure SSE event reducer for the workspace stream session.
 *
 * Extracted from WorkspaceRouteRoot.handleStreamEvent (Phase 3.1) so that
 * stream-event handling is deterministic, snapshot-testable, and decoupled
 * from React state setters / refs / DOM timing.
 *
 * Contract:
 * - 100% pure: no Date.now(), Math.random(), fetch, DOM, console, or refs.
 *   Time and tool-id seeds enter through {@link StreamReducerContext.now}
 *   and the state-level {@link StreamReducerState.nextToolId} counter.
 * - Mirrors FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT for the `text` event:
 *   the collector buffers run-aware text into the active assistant message;
 *   speculative head_supervisor approval is enforced on the backend, so by
 *   the time a `text` event reaches this reducer it is always canonical.
 *   The reducer therefore appends `text` only into the approved assistant
 *   bubble identified by {@link StreamReducerContext.assistantMsgId} and
 *   never concats speculative buffers across runs.
 * - All side effects (router.push, autoscroll, telemetry refresh, toasts)
 *   stay in the caller; this reducer only produces a new state value.
 */
import type { StreamEvent, ToolExecution } from '@/types/agent';
import type {
  ActionSpaceState,
  ActiveThreadState,
  StreamSessionState,
  ThreadCollectionState,
} from '@/types/thread';
import { appendAssistantText, pushUniqueHistory } from '@/lib/chat-stream';
import { patchThreadSummary } from '@/lib/workspace-state';

/**
 * Combined state shape consumed and produced by {@link reduceStreamEvent}.
 *
 * Each slice maps 1:1 with the React state slot in WorkspaceRouteRoot:
 *   - threadCollection -> setThreadCollectionState
 *   - activeThread     -> setActiveThreadState
 *   - streamSession    -> setStreamSessionState
 *   - actionSpace      -> setActionSpaceState
 *
 * `nextToolId` is the monotonically increasing counter that previously lived
 * on `toolIdCounterRef`. Lifting it into the reducer state keeps tool ids
 * deterministic and the reducer pure.
 */
export interface StreamReducerState {
  threadCollection: ThreadCollectionState;
  activeThread: ActiveThreadState;
  streamSession: StreamSessionState;
  actionSpace: ActionSpaceState;
  nextToolId: number;
}

/**
 * Per-call context for the reducer.
 *
 * - `assistantMsgId`: id of the assistant bubble that text/error chunks
 *   should be appended to. The caller (WorkspaceRouteRoot) generates this
 *   id when it starts a turn and passes it through for the whole stream.
 * - `threadId`: thread the stream belongs to. Used to scope
 *   `patchThreadSummary` updates.
 * - `now`: timestamp (ms epoch) used for tool execution start/end times.
 *   Pass `Date.now()` from the caller — keeping it out of the reducer makes
 *   the reducer pure and snapshot-friendly.
 */
export interface StreamReducerContext {
  assistantMsgId: string;
  threadId: string;
  now: number;
}

function appendReasoningEntry(
  entries: ActionSpaceState['reasoningEntries'],
  payload: {
    node?: string | null;
    display_name?: string | null;
    content: string;
    timestamp: string;
    run_id?: string;
  }
): ActionSpaceState['reasoningEntries'] {
  const nextEntries = [...entries];
  const mergeTargetId =
    payload.run_id || `${payload.node || 'reasoning'}:${payload.timestamp}`;
  const lastEntry = nextEntries[nextEntries.length - 1];

  if (lastEntry && payload.run_id && lastEntry.runId === payload.run_id) {
    nextEntries[nextEntries.length - 1] = {
      ...lastEntry,
      content: lastEntry.content + payload.content,
      timestamp: payload.timestamp || lastEntry.timestamp,
    };
    return nextEntries;
  }

  nextEntries.push({
    id: mergeTargetId,
    node: payload.node,
    displayName: payload.display_name,
    content: payload.content,
    timestamp: payload.timestamp,
    runId: payload.run_id,
  });
  return nextEntries;
}

/**
 * Resolve which `toolExecutions` entry an end/error event refers to.
 *
 * Strategy mirrors the original handler:
 *   1. If `run_id` is present, prefer the latest running entry with the same
 *      run_id (this is the only reliable correlation key).
 *   2. Otherwise fall back to the latest running entry whose display name
 *      matches the event's display name.
 * Returns -1 when no match is found so the caller can no-op.
 */
function findToolExecutionIndex(
  toolExecutions: ToolExecution[],
  runId: string | undefined,
  targetName: string
): number {
  if (runId) {
    for (let i = toolExecutions.length - 1; i >= 0; i -= 1) {
      const exec = toolExecutions[i];
      if (exec.runId === runId && exec.status === 'running') {
        return i;
      }
    }
  }

  for (let i = toolExecutions.length - 1; i >= 0; i -= 1) {
    const exec = toolExecutions[i];
    if (exec.name === targetName && exec.status === 'running') {
      return i;
    }
  }

  return -1;
}

function appendAttachmentsToLastRole(
  messages: ActiveThreadState['messages'],
  role: 'assistant' | 'user',
  attachments: ActiveThreadState['messages'][number]['attachments']
): ActiveThreadState['messages'] {
  const next = [...messages];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === role) {
      next[i] = {
        ...next[i],
        attachments,
      };
      break;
    }
  }
  return next;
}

/**
 * Pure SSE event reducer. Given the current combined workspace state and a
 * single SSE event, return the next state. The caller is responsible for
 * propagating each slice back to React via individual setState calls.
 *
 * The function ALWAYS returns a fresh `actionSpace.rawTraces` array
 * containing the incoming event so the debug panel stays in sync, regardless
 * of which branch handles the event.
 */
export function reduceStreamEvent(
  state: StreamReducerState,
  event: StreamEvent,
  ctx: StreamReducerContext
): StreamReducerState {
  // Every event is appended to the raw trace stream for debug surfaces.
  const baseActionSpace: ActionSpaceState = {
    ...state.actionSpace,
    rawTraces: [...state.actionSpace.rawTraces, event],
  };

  switch (event.event_type) {
    case 'status': {
      const nextThreads = patchThreadSummary(
        state.threadCollection.threads,
        ctx.threadId,
        {
          latest_status: event.status,
          last_activity_at: event.timestamp,
        }
      );

      let nextStreamSession: StreamSessionState = {
        ...state.streamSession,
        loading: event.status === 'running',
      };

      if (event.status === 'completed') {
        nextStreamSession = {
          ...nextStreamSession,
          currentNode: 'Completed',
          isInterrupted: false,
        };
      } else if (event.status === 'errored') {
        nextStreamSession = {
          ...nextStreamSession,
          currentNode: 'Errored',
          isInterrupted: false,
          streamError: event.message || state.streamSession.streamError,
        };
      } else if (event.status === 'interrupted') {
        nextStreamSession = {
          ...nextStreamSession,
          currentNode: 'Requires User Action',
          isInterrupted: true,
          loading: false,
        };
      } else if (event.display_name) {
        nextStreamSession = {
          ...nextStreamSession,
          currentNode: event.display_name,
          isInterrupted: false,
        };
      }

      return {
        ...state,
        threadCollection: {
          ...state.threadCollection,
          threads: nextThreads,
        },
        activeThread: {
          ...state.activeThread,
          latestStatus: event.status,
          lastActivityAt: event.timestamp,
        },
        streamSession: nextStreamSession,
        actionSpace: baseActionSpace,
      };
    }

    case 'route': {
      const nextDisplay = event.display_name || event.target || '';
      if (!nextDisplay || event.target === 'FINISH') {
        return { ...state, actionSpace: baseActionSpace };
      }

      return {
        ...state,
        streamSession: {
          ...state.streamSession,
          currentNode: nextDisplay,
          history: pushUniqueHistory(state.streamSession.history, nextDisplay),
        },
        actionSpace: baseActionSpace,
      };
    }

    case 'tool_start': {
      const id = `tool_${state.nextToolId}`;
      const newTool: ToolExecution = {
        id,
        runId: event.run_id,
        name: event.display_name || event.tool_name || event.node || 'Tool',
        toolName: event.tool_name || event.node || undefined,
        status: 'running',
        input: event.input,
        startTime: ctx.now,
      };

      return {
        ...state,
        actionSpace: {
          ...baseActionSpace,
          toolExecutions: [...baseActionSpace.toolExecutions, newTool],
        },
        nextToolId: state.nextToolId + 1,
      };
    }

    case 'tool_end': {
      const targetName =
        event.display_name || event.tool_name || event.node || 'Tool';
      const next = [...baseActionSpace.toolExecutions];
      const idx = findToolExecutionIndex(next, event.run_id, targetName);

      if (idx !== -1) {
        next[idx] = {
          ...next[idx],
          status: 'success',
          output: event.output,
          endTime: ctx.now,
        };
      }

      return {
        ...state,
        actionSpace: {
          ...baseActionSpace,
          toolExecutions: next,
        },
      };
    }

    case 'tool_error': {
      const targetName =
        event.display_name || event.tool_name || event.node || 'Tool';
      const next = [...baseActionSpace.toolExecutions];
      const idx = findToolExecutionIndex(next, event.run_id, targetName);

      if (idx !== -1) {
        next[idx] = {
          ...next[idx],
          status: 'error',
          output: event.error,
          endTime: ctx.now,
        };
      }

      return {
        ...state,
        actionSpace: {
          ...baseActionSpace,
          toolExecutions: next,
        },
      };
    }

    case 'reasoning': {
      return {
        ...state,
        actionSpace: {
          ...baseActionSpace,
          reasoning: baseActionSpace.reasoning + event.content,
          reasoningEntries: appendReasoningEntry(
            baseActionSpace.reasoningEntries,
            event
          ),
        },
      };
    }

    case 'text': {
      // FINAL_RESPONSE_STREAM_OWNERSHIP_CONTRACT:
      //   - Backend ensures only the approved final-answer owner emits `text`
      //     events to the user channel (head_supervisor speculative buffers
      //     are filtered server-side per Decisions 2 & 4).
      //   - This reducer therefore appends `text` content exclusively to the
      //     single assistant bubble identified by ctx.assistantMsgId, never
      //     concatenating across runs (Decision 5: forbidden mixing).
      //   - thread preview mirrors the same canonical content.
      const trimmed = event.content.trim();
      const nextThreads = patchThreadSummary(
        state.threadCollection.threads,
        ctx.threadId,
        {
          preview: trimmed || undefined,
          last_activity_at: event.timestamp,
        }
      );

      return {
        ...state,
        threadCollection: {
          ...state.threadCollection,
          threads: nextThreads,
        },
        activeThread: {
          ...state.activeThread,
          messages: appendAssistantText(
            state.activeThread.messages,
            ctx.assistantMsgId,
            event.content
          ),
          lastActivityAt: event.timestamp,
        },
        actionSpace: baseActionSpace,
      };
    }

    case 'attachments': {
      return {
        ...state,
        activeThread: {
          ...state.activeThread,
          messages: appendAttachmentsToLastRole(
            state.activeThread.messages,
            event.role,
            event.attachments
          ),
        },
        actionSpace: baseActionSpace,
      };
    }

    case 'checkpoint': {
      const nextThreads = patchThreadSummary(
        state.threadCollection.threads,
        ctx.threadId,
        {
          checkpoint_id: event.checkpoint_id || null,
        }
      );

      return {
        ...state,
        threadCollection: {
          ...state.threadCollection,
          threads: nextThreads,
        },
        activeThread: {
          ...state.activeThread,
          checkpointId: event.checkpoint_id || '',
        },
        actionSpace: baseActionSpace,
      };
    }

    case 'error': {
      return {
        ...state,
        streamSession: {
          ...state.streamSession,
          loading: false,
          currentNode: 'Errored',
          streamError: event.message,
        },
        activeThread: {
          ...state.activeThread,
          messages: appendAssistantText(
            state.activeThread.messages,
            `${ctx.assistantMsgId}_error`,
            `Error: ${event.message}`
          ),
          latestStatus: 'errored',
        },
        actionSpace: baseActionSpace,
      };
    }

    default: {
      // Unknown event types still flow into rawTraces so the debug panel
      // surfaces them, but no other slice is touched.
      return { ...state, actionSpace: baseActionSpace };
    }
  }
}
