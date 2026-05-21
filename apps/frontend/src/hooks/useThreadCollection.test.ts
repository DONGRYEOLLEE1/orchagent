/**
 * useThreadCollection — unit tests (Phase 3.2).
 *
 * Covers the optimistic insert / remove transitions on the sidebar slice.
 * The mount-effect fetch is stubbed to a deterministic empty list so the
 * assertions focus on the synchronous reducer-like helpers.
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
    mockedFetchThreads.mockResolvedValue([]);
  });

  it('addOptimisticThread upserts a thread summary at the top of the list', async () => {
    const { result } = renderHook(() => useThreadCollection());

    await waitFor(() => {
      expect(result.current.threadCollection.loadState).toBe('success');
    });

    const summary = makeSummary({
      thread_id: 't-1',
      title: 'New thread',
      last_activity_at: '2026-05-21T10:00:00Z',
    });

    act(() => {
      result.current.addOptimisticThread(summary);
    });

    expect(result.current.threadCollection.threads).toHaveLength(1);
    expect(result.current.threadCollection.threads[0].thread_id).toBe('t-1');
    expect(result.current.threadCollection.error).toBe('');
  });

  it('removeThread drops the matching summary from local state without an API call', async () => {
    mockedFetchThreads.mockResolvedValueOnce([
      makeSummary({ thread_id: 't-a' }),
      makeSummary({ thread_id: 't-b' }),
    ]);

    const { result } = renderHook(() => useThreadCollection());

    await waitFor(() => {
      expect(result.current.threadCollection.threads).toHaveLength(2);
    });

    act(() => {
      result.current.removeThread('t-a');
    });

    expect(result.current.threadCollection.threads).toHaveLength(1);
    expect(result.current.threadCollection.threads[0].thread_id).toBe('t-b');
  });
});
