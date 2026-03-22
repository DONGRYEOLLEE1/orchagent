import { expect, test } from 'vitest';

import {
  applyThreadSummaryToActiveThread,
  createActiveThreadStateFromDetail,
  createHistoricalStreamSessionState,
  createInitialActiveThreadState,
  createOptimisticThreadSummary,
  upsertThreadSummary,
} from '@/lib/workspace-state';
import type { ThreadDetail, ThreadSummary } from '@/types/thread';

test('creates optimistic thread summaries and moves them to the top', () => {
  const older: ThreadSummary = {
    thread_id: 'thread-old',
    title: 'Older thread',
    preview: 'Older preview',
    created_at: '2026-03-22T08:00:00Z',
    last_activity_at: '2026-03-22T08:10:00Z',
    message_count: 1,
    latest_status: 'completed',
    checkpoint_id: 'cp-old',
  };

  const optimistic = createOptimisticThreadSummary({
    threadId: 'thread-live',
    content: 'A fresh prompt for a new conversation',
  });

  const reordered = upsertThreadSummary([older], optimistic);

  expect(optimistic.title).toContain('A fresh prompt');
  expect(optimistic.latest_status).toBe('running');
  expect(reordered.map((thread) => thread.thread_id)).toEqual([
    'thread-live',
    'thread-old',
  ]);
});

test('hydrates active thread state from detail and summary metadata', () => {
  const detail: ThreadDetail = {
    thread: {
      thread_id: 'thread-1',
      title: 'Thread title',
      preview: 'Preview',
      created_at: '2026-03-22T10:00:00Z',
      last_activity_at: '2026-03-22T10:20:00Z',
      message_count: 2,
      latest_status: 'interrupted',
      checkpoint_id: 'cp-1',
    },
    messages: [
      {
        id: 'm-1',
        role: 'user',
        content: 'hello',
        created_at: '2026-03-22T10:00:00Z',
      },
      {
        id: 'm-2',
        role: 'assistant',
        content: 'hi',
        created_at: '2026-03-22T10:01:00Z',
      },
    ],
  };

  const hydrated = createActiveThreadStateFromDetail(detail);
  const updated = applyThreadSummaryToActiveThread(hydrated, {
    ...detail.thread,
    latest_status: 'completed',
    checkpoint_id: 'cp-2',
  });

  expect(hydrated.viewMode).toBe('historical');
  expect(hydrated.messages).toHaveLength(2);
  expect(updated.latestStatus).toBe('completed');
  expect(updated.checkpointId).toBe('cp-2');
});

test('builds historical stream state from latest status', () => {
  expect(createHistoricalStreamSessionState('interrupted')).toMatchObject({
    currentNode: 'Requires User Action',
    isInterrupted: true,
  });
  expect(createHistoricalStreamSessionState('completed')).toMatchObject({
    currentNode: 'Completed',
    isInterrupted: false,
  });
  expect(createHistoricalStreamSessionState(null)).toMatchObject({
    currentNode: '',
    isInterrupted: false,
  });
  expect(createInitialActiveThreadState().viewMode).toBe('draft');
});
