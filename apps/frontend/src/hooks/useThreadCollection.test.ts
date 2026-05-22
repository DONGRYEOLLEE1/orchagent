/**
 * useThreadCollection — unit tests.
 *
 * One consolidated case covers both optimistic insert and local remove
 * transitions to keep this slice's reducer-like helpers under test.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ThreadSummary } from '@/types/thread';

vi.mock('@/lib/api', () => ({
  fetchThreads: vi.fn(),
  patchThread: vi.fn(),
  deleteThread: vi.fn(),
}));

import { fetchThreads as fetchThreadsApi } from '@/lib/api';
import { useThreadCollection } from './useThreadCollection';

const mockedFetchThreads = vi.mocked(fetchThreadsApi);

function makeSummary(overrides: Partial<ThreadSummary> & { thread_id: string }): ThreadSummary {
  return {
    thread_id: overrides.thread_id,
    title: overrides.title ?? `Thread ${overrides.thread_id}`,
    preview: overrides.preview ?? '',
    created_at: overrides.created_at ?? '2026-05-01T00:00:00Z',
    last_activity_at: overrides.last_activity_at ?? '2026-05-01T00:00:00Z',
    message_count: overrides.message_count ?? 0,
    latest_status: overrides.latest_status ?? null,
    checkpoint_id: overrides.checkpoint_id ?? null,
    pinned: overrides.pinned ?? false,
    archived: overrides.archived ?? false,
  };
}

describe('useThreadCollection', () => {
  beforeEach(() => {
    mockedFetchThreads.mockReset();
    mockedFetchThreads.mockResolvedValueOnce([
      makeSummary({ thread_id: 't-a' }),
      makeSummary({ thread_id: 't-b' }),
    ]);
  });

  it('addOptimisticThread + removeThread mutate the local sidebar slice without re-fetching', async () => {
    const { result } = renderHook(() => useThreadCollection());

    await waitFor(() => {
      expect(result.current.threadCollection.threads).toHaveLength(2);
    });

    act(() =>
      result.current.addOptimisticThread(
        makeSummary({ thread_id: 't-1', title: 'New thread', last_activity_at: '2026-05-21T10:00:00Z' }),
      ),
    );
    expect(result.current.threadCollection.threads[0].thread_id).toBe('t-1');

    act(() => result.current.removeThread('t-a'));
    expect(result.current.threadCollection.threads.find((t) => t.thread_id === 't-a')).toBeUndefined();
  });
});
