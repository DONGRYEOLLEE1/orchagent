import { describe, expect, test } from 'vitest';

import {
  reduceStreamEvent,
  type StreamReducerContext,
  type StreamReducerState,
} from '@/lib/sse-reducer';
import {
  createInitialActionSpaceState,
  createInitialActiveThreadState,
  createInitialStreamSessionState,
  createInitialThreadCollectionState,
} from '@/lib/workspace-state';
import type {
  StreamAttachmentEvent,
  StreamCheckpointEvent,
  StreamErrorEvent,
  StreamRouteEvent,
  StreamStatusEvent,
  StreamTextEvent,
  StreamToolEvent,
} from '@/types/agent';
import type { ThreadSummary } from '@/types/thread';

function makeThreadSummary(threadId: string): ThreadSummary {
  return {
    thread_id: threadId,
    title: 'Test thread',
    preview: 'preview',
    created_at: '2026-05-21T00:00:00.000Z',
    last_activity_at: '2026-05-21T00:00:00.000Z',
    message_count: 1,
    latest_status: 'idle',
    checkpoint_id: null,
    pinned: false,
    archived: false,
  };
}

function makeBaseState(threadId = 'thread-1'): StreamReducerState {
  return {
    threadCollection: {
      ...createInitialThreadCollectionState(),
      threads: [makeThreadSummary(threadId)],
    },
    activeThread: {
      ...createInitialActiveThreadState(),
      threadId,
    },
    streamSession: createInitialStreamSessionState(),
    actionSpace: createInitialActionSpaceState(),
    nextToolId: 0,
  };
}

const CTX: StreamReducerContext = {
  assistantMsgId: 'assistant_1',
  threadId: 'thread-1',
  now: 1_700_000_000_000,
};

describe('reduceStreamEvent — status transitions', () => {
  test('running → interrupted → errored: flips loading + node + status surfaces are wired correctly', () => {
    // Consolidates three prior status sub-cases into one sequential transition.
    const running: StreamStatusEvent = {
      event_type: 'status',
      status: 'running',
      thread_id: 'thread-1',
      display_name: 'Head Supervisor',
      timestamp: '2026-05-21T00:00:01.000Z',
    };
    const interrupted: StreamStatusEvent = {
      event_type: 'status',
      status: 'interrupted',
      thread_id: 'thread-1',
      timestamp: '2026-05-21T00:00:02.000Z',
    };
    const errored: StreamStatusEvent = {
      event_type: 'status',
      status: 'errored',
      thread_id: 'thread-1',
      message: 'upstream timeout',
      timestamp: '2026-05-21T00:00:03.000Z',
    };

    let s = reduceStreamEvent(makeBaseState(), running, CTX);
    expect(s.streamSession.loading).toBe(true);
    expect(s.streamSession.currentNode).toBe('Head Supervisor');
    expect(s.activeThread.latestStatus).toBe('running');
    expect(s.activeThread.lastActivityAt).toBe(running.timestamp);
    expect(s.threadCollection.threads[0].latest_status).toBe('running');

    s = reduceStreamEvent(s, interrupted, CTX);
    expect(s.streamSession.loading).toBe(false);
    expect(s.streamSession.isInterrupted).toBe(true);
    expect(s.streamSession.currentNode).toBe('Requires User Action');

    s = reduceStreamEvent(s, errored, CTX);
    expect(s.streamSession.currentNode).toBe('Errored');
    expect(s.streamSession.streamError).toBe('upstream timeout');
    expect(s.streamSession.isInterrupted).toBe(false);
  });
});

describe('reduceStreamEvent — route', () => {
  test('route advances currentNode + history; target=FINISH preserves currentNode but still traces', () => {
    const team: StreamRouteEvent = {
      event_type: 'route',
      target: 'research_team',
      display_name: 'Research Team',
      timestamp: '2026-05-21T00:00:03.000Z',
    };
    const finish: StreamRouteEvent = {
      event_type: 'route',
      target: 'FINISH',
      display_name: 'Finish',
      timestamp: '2026-05-21T00:00:04.000Z',
    };

    const a = reduceStreamEvent(makeBaseState(), team, CTX);
    expect(a.streamSession.currentNode).toBe('Research Team');
    expect(a.streamSession.history).toEqual(['Research Team']);

    const b = reduceStreamEvent(a, finish, CTX);
    // FINISH must not overwrite currentNode but must still trace.
    expect(b.streamSession.currentNode).toBe('Research Team');
    expect(b.actionSpace.rawTraces).toHaveLength(2);
  });
});

describe('reduceStreamEvent — tool lifecycle', () => {
  test('tool_start assigns deterministic id; tool_end → success; tool_error → error', () => {
    const start: StreamToolEvent = {
      event_type: 'tool_start',
      tool_name: 'web_search',
      display_name: 'Web Search',
      node: 'research_team',
      run_id: 'run_42',
      input: { query: 'orchagent' },
      timestamp: '2026-05-21T00:00:05.000Z',
    };
    const end: StreamToolEvent = {
      event_type: 'tool_end',
      tool_name: 'web_search',
      display_name: 'Web Search',
      run_id: 'run_42',
      output: 'OK',
      timestamp: '2026-05-21T00:00:06.000Z',
    };

    let s = reduceStreamEvent({ ...makeBaseState(), nextToolId: 7 }, start, CTX);
    expect(s.nextToolId).toBe(8);
    expect(s.actionSpace.toolExecutions[0]).toMatchObject({
      id: 'tool_7',
      runId: 'run_42',
      name: 'Web Search',
      toolName: 'web_search',
      status: 'running',
      startTime: CTX.now,
    });

    s = reduceStreamEvent(s, end, { ...CTX, now: CTX.now + 1000 });
    expect(s.actionSpace.toolExecutions[0]).toMatchObject({
      status: 'success',
      output: 'OK',
      endTime: CTX.now + 1000,
    });

    // Verify error pathway in a separate flow so the matched run_id branch is exercised.
    const errStart: StreamToolEvent = {
      event_type: 'tool_start',
      tool_name: 'shell',
      display_name: 'Shell',
      run_id: 'run_err',
      timestamp: '2026-05-21T00:00:08.000Z',
    };
    const errEvent: StreamToolEvent = {
      event_type: 'tool_error',
      tool_name: 'shell',
      display_name: 'Shell',
      run_id: 'run_err',
      error: 'permission denied',
      timestamp: '2026-05-21T00:00:09.000Z',
    };

    const afterStart = reduceStreamEvent(makeBaseState(), errStart, CTX);
    const afterErr = reduceStreamEvent(afterStart, errEvent, CTX);
    expect(afterErr.actionSpace.toolExecutions[0]).toMatchObject({
      status: 'error',
      output: 'permission denied',
    });
  });
});

describe('reduceStreamEvent — reasoning', () => {
  test('reasoning chunks concatenate per run_id into a single entry', () => {
    const e1: StreamTextEvent = {
      event_type: 'reasoning',
      run_id: 'reason_1',
      node: 'head_supervisor',
      content: 'Step 1.',
      timestamp: '2026-05-21T00:00:10.000Z',
    };
    const e2: StreamTextEvent = {
      event_type: 'reasoning',
      run_id: 'reason_1',
      node: 'head_supervisor',
      content: ' Step 2.',
      timestamp: '2026-05-21T00:00:11.000Z',
    };

    const b = reduceStreamEvent(reduceStreamEvent(makeBaseState(), e1, CTX), e2, CTX);
    expect(b.actionSpace.reasoning).toBe('Step 1. Step 2.');
    expect(b.actionSpace.reasoningEntries).toHaveLength(1);
    expect(b.actionSpace.reasoningEntries[0].content).toBe('Step 1. Step 2.');
  });
});

describe('reduceStreamEvent — text (FINAL_RESPONSE_STREAM_OWNERSHIP)', () => {
  // The three sub-cases below are explicitly preserved — they encode the
  // FINAL_RESPONSE_STREAM_OWNERSHIP contract that prevents speculative
  // head_supervisor text from leaking into the finalizer bubble.

  test('text appends only to the approved assistant bubble identified by ctx.assistantMsgId', () => {
    const event: StreamTextEvent = {
      event_type: 'text',
      content: 'Hello',
      timestamp: '2026-05-21T00:00:12.000Z',
    };

    const next = reduceStreamEvent(makeBaseState(), event, CTX);

    expect(next.activeThread.messages).toHaveLength(1);
    expect(next.activeThread.messages[0]).toMatchObject({
      id: CTX.assistantMsgId,
      role: 'assistant',
      content: 'Hello',
    });
    expect(next.activeThread.lastActivityAt).toBe(event.timestamp);
    expect(next.threadCollection.threads[0].preview).toBe('Hello');
  });

  test('multiple text chunks for the same assistantMsgId concat into a single bubble (no cross-run mixing)', () => {
    const chunk1: StreamTextEvent = {
      event_type: 'text',
      content: 'Hello',
      timestamp: '2026-05-21T00:00:13.000Z',
    };
    const chunk2: StreamTextEvent = {
      event_type: 'text',
      content: ', world!',
      timestamp: '2026-05-21T00:00:14.000Z',
    };

    const b = reduceStreamEvent(reduceStreamEvent(makeBaseState(), chunk1, CTX), chunk2, CTX);
    expect(b.activeThread.messages).toHaveLength(1);
    expect(b.activeThread.messages[0].content).toBe('Hello, world!');
  });

  test('switching ctx.assistantMsgId (new approved owner) starts a new bubble', () => {
    // Decision 5: speculative head_supervisor text and finalizer text MUST NOT
    // be concatenated. When the canonical owner changes, a new assistantMsgId
    // is passed in and the reducer opens a fresh assistant bubble.
    const chunk1: StreamTextEvent = {
      event_type: 'text',
      content: 'speculative',
      timestamp: '2026-05-21T00:00:15.000Z',
    };
    const chunk2: StreamTextEvent = {
      event_type: 'text',
      content: 'final',
      timestamp: '2026-05-21T00:00:16.000Z',
    };

    const a = reduceStreamEvent(makeBaseState(), chunk1, { ...CTX, assistantMsgId: 'spec_owner' });
    const b = reduceStreamEvent(a, chunk2, { ...CTX, assistantMsgId: 'final_owner' });

    expect(b.activeThread.messages).toHaveLength(2);
    expect(b.activeThread.messages.map((m) => m.id)).toEqual(['spec_owner', 'final_owner']);
    expect(b.activeThread.messages[1].content).toBe('final');
  });
});

describe('reduceStreamEvent — attachments', () => {
  test('attachments attach to the most recent message matching role + message_id', () => {
    const baseWithMessage: StreamReducerState = {
      ...makeBaseState(),
      activeThread: {
        ...makeBaseState().activeThread,
        messages: [
          { id: 'u1', role: 'user', content: 'see attached' },
          { id: 'a1', role: 'assistant', content: 'sure' },
        ],
      },
    };
    const event: StreamAttachmentEvent = {
      event_type: 'attachments',
      role: 'user',
      message_id: 'u1',
      attachments: [{ kind: 'image', alt: 'photo' }],
      timestamp: '2026-05-21T00:00:17.000Z',
    };

    const next = reduceStreamEvent(baseWithMessage, event, CTX);
    expect(next.activeThread.messages[0].attachments).toEqual([{ kind: 'image', alt: 'photo' }]);
    expect(next.activeThread.messages[1].attachments).toBeUndefined();
  });
});

describe('reduceStreamEvent — checkpoint', () => {
  test('checkpoint event syncs checkpoint_id into active thread + thread summary', () => {
    const event: StreamCheckpointEvent = {
      event_type: 'checkpoint',
      thread_id: 'thread-1',
      checkpoint_id: 'ckpt_abc',
      timestamp: '2026-05-21T00:00:18.000Z',
    };

    const next = reduceStreamEvent(makeBaseState(), event, CTX);
    expect(next.activeThread.checkpointId).toBe('ckpt_abc');
    expect(next.threadCollection.threads[0].checkpoint_id).toBe('ckpt_abc');
  });
});

describe('reduceStreamEvent — error', () => {
  test('error event opens a separate error bubble and marks thread errored', () => {
    const event: StreamErrorEvent = {
      event_type: 'error',
      message: 'fatal: connection reset',
      timestamp: '2026-05-21T00:00:19.000Z',
    };

    const next = reduceStreamEvent(makeBaseState(), event, CTX);

    expect(next.streamSession.loading).toBe(false);
    expect(next.streamSession.currentNode).toBe('Errored');
    expect(next.streamSession.streamError).toBe('fatal: connection reset');
    expect(next.activeThread.latestStatus).toBe('errored');
    expect(next.activeThread.messages).toHaveLength(1);
    expect(next.activeThread.messages[0].id).toBe(`${CTX.assistantMsgId}_error`);
    expect(next.activeThread.messages[0].content).toBe('Error: fatal: connection reset');
  });
});

describe('reduceStreamEvent — purity invariants', () => {
  test('reducer is pure (no input mutation) and appends exactly one rawTrace per event', () => {
    const state = makeBaseState();
    const snapshotThreads = state.threadCollection.threads;
    const snapshotMessages = state.activeThread.messages;
    const snapshotTraces = state.actionSpace.rawTraces;

    const events = [
      { event_type: 'status', status: 'running', thread_id: 'thread-1', timestamp: 't1' } as StreamStatusEvent,
      { event_type: 'route', target: 'team', display_name: 'Team', timestamp: 't2' } as StreamRouteEvent,
      { event_type: 'reasoning', content: 'x', timestamp: 't3' } as StreamTextEvent,
      { event_type: 'checkpoint', thread_id: 'thread-1', timestamp: 't4' } as StreamCheckpointEvent,
    ];

    let next = state;
    for (const ev of events) {
      next = reduceStreamEvent(next, ev, CTX);
    }

    expect(next.actionSpace.rawTraces).toHaveLength(events.length);
    // Original references must remain untouched.
    expect(state.threadCollection.threads).toBe(snapshotThreads);
    expect(state.activeThread.messages).toBe(snapshotMessages);
    expect(state.actionSpace.rawTraces).toBe(snapshotTraces);
  });
});
