/**
 * useActiveThread — unit tests.
 *
 * Consolidated case exercises both helpers (appendMessage + applySummary) in
 * one render, plus verifies summaries for other thread ids are ignored.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatMessage } from '@/types/agent';
import type { ThreadSummary } from '@/types/thread';

vi.mock('@/lib/api', () => ({
  fetchThreadDetail: vi.fn(),
}));

import { useActiveThread } from './useActiveThread';

function makeSummary(overrides: Partial<ThreadSummary> & { thread_id: string }): ThreadSummary {
  return {
    thread_id: overrides.thread_id,
    title: overrides.title ?? 'Active thread',
    preview: overrides.preview ?? 'preview text',
    created_at: overrides.created_at ?? '2026-05-21T08:00:00Z',
    last_activity_at: overrides.last_activity_at ?? '2026-05-21T09:00:00Z',
    message_count: overrides.message_count ?? 4,
    latest_status: overrides.latest_status ?? 'completed',
    checkpoint_id: overrides.checkpoint_id ?? 'ckpt-1',
    pinned: overrides.pinned ?? false,
    archived: overrides.archived ?? false,
  };
}

describe('useActiveThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('appendMessage + applySummary update the active slice; non-matching summaries are ignored', () => {
    const { result } = renderHook(() => useActiveThread());

    act(() => result.current.beginLoadingThread('t-1'));
    expect(result.current.activeThread.threadId).toBe('t-1');

    const message: ChatMessage = { id: 'u-1', role: 'user', content: 'hello' };
    act(() => result.current.appendMessage(message));
    expect(result.current.activeThread.messages).toEqual([message]);

    act(() =>
      result.current.applySummary(
        makeSummary({ thread_id: 't-1', title: 'renamed by ai', checkpoint_id: 'ckpt-99' }),
      ),
    );
    expect(result.current.activeThread.title).toBe('renamed by ai');
    expect(result.current.activeThread.checkpointId).toBe('ckpt-99');

    // Non-matching summary must be a no-op for the active slice.
    act(() => result.current.applySummary(makeSummary({ thread_id: 't-2', title: 'unrelated' })));
    expect(result.current.activeThread.title).toBe('renamed by ai');
  });
});
