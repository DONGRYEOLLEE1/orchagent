import { expect, test } from 'vitest';

import {
  applyThreadSummaryToActiveThread,
  createActiveThreadStateFromDetail,
  createHistoricalStreamSessionState,
  createInitialActiveThreadState,
  createOptimisticThreadSummary,
  patchThreadSummary,
  sortThreadSummaries,
  upsertThreadSummary,
} from '@/lib/workspace-state';
import type { ThreadDetail, ThreadSummary } from '@/types/thread';

function summary(overrides: Partial<ThreadSummary> & { thread_id: string }): ThreadSummary {
  return {
    thread_id: overrides.thread_id,
    title: overrides.title ?? `Thread ${overrides.thread_id}`,
    preview: overrides.preview ?? 'preview',
    created_at: overrides.created_at ?? '2026-03-22T08:00:00Z',
    last_activity_at: overrides.last_activity_at ?? '2026-03-22T09:00:00Z',
    message_count: overrides.message_count ?? 1,
    latest_status: overrides.latest_status ?? 'completed',
    checkpoint_id: overrides.checkpoint_id ?? 'cp-x',
    pinned: overrides.pinned ?? false,
    archived: overrides.archived ?? false,
  };
}

test('thread-collection sort/insert/patch helpers honour pinned-first + recency ordering', () => {
  // Consolidates three prior cases (`creates optimistic`, `sorts pinned`,
  // `patchThreadSummary reorders pinned threads to the top`) into one
  // sequential exercise of the public helpers on the same fixture.

  // upsertThreadSummary places an optimistic new thread at the top.
  const older = summary({ thread_id: 'thread-old', title: 'Older thread', last_activity_at: '2026-03-22T08:10:00Z' });
  const optimistic = createOptimisticThreadSummary({
    threadId: 'thread-live',
    content: 'A fresh prompt for a new conversation',
  });
  const upserted = upsertThreadSummary([older], optimistic);
  expect(optimistic.latest_status).toBe('running');
  expect(upserted.map((t) => t.thread_id)).toEqual(['thread-live', 'thread-old']);

  // sortThreadSummaries puts pinned threads ahead of newer unpinned ones.
  const sorted = sortThreadSummaries([
    summary({ thread_id: 'unpinned', last_activity_at: '2026-03-22T12:00:00Z' }),
    summary({ thread_id: 'pinned-old', pinned: true, last_activity_at: '2026-03-22T09:00:00Z' }),
  ]);
  expect(sorted.map((t) => t.thread_id)).toEqual(['pinned-old', 'unpinned']);

  // patchThreadSummary toggling pinned=true moves a thread to the top.
  const patched = patchThreadSummary(
    [
      summary({ thread_id: 'a', last_activity_at: '2026-03-22T12:00:00Z' }),
      summary({ thread_id: 'b', last_activity_at: '2026-03-22T09:00:00Z' }),
    ],
    'b',
    { pinned: true },
  );
  expect(patched.map((t) => t.thread_id)).toEqual(['b', 'a']);
});

test('hydrates active-thread slice from ThreadDetail and re-applies summary metadata', () => {
  const detail: ThreadDetail = {
    thread: summary({ thread_id: 'thread-1', title: 'Thread title', latest_status: 'interrupted', checkpoint_id: 'cp-1', message_count: 2, last_activity_at: '2026-03-22T10:20:00Z', created_at: '2026-03-22T10:00:00Z' }),
    messages: [
      {
        id: 'm-1',
        role: 'user',
        content: 'hello',
        created_at: '2026-03-22T10:00:00Z',
        attachments: [
          {
            kind: 'image',
            url: 'http://localhost:8002/api/threads/thread-1/messages/m-1/attachments/0',
            alt: '첨부 이미지 1',
          },
        ],
      },
      { id: 'm-2', role: 'assistant', content: 'hi', created_at: '2026-03-22T10:01:00Z' },
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
  expect(hydrated.messages[0].attachments).toHaveLength(1);
  expect(updated.latestStatus).toBe('completed');
  expect(updated.checkpointId).toBe('cp-2');
});

test('builds historical stream state from latest status; initial active state defaults to draft', () => {
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
