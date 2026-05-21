/**
 * useActiveThread — unit tests (Phase 3.2).
 *
 * Covers message append + summary apply transitions. Network access is
 * mocked so the slice transitions can be asserted in isolation.
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

  it('appendMessage pushes the new chat message onto the active slice', () => {
    const { result } = renderHook(() => useActiveThread());

    act(() => {
      result.current.beginLoadingThread('t-1');
    });

    expect(result.current.activeThread.threadId).toBe('t-1');
    expect(result.current.activeThread.messages).toHaveLength(0);

    const message: ChatMessage = {
      id: 'u-1',
      role: 'user',
      content: 'hello',
    };

    act(() => {
      result.current.appendMessage(message);
    });

    expect(result.current.activeThread.messages).toEqual([message]);
  });

  it('applySummary refreshes title/checkpoint when the summary matches the active thread', () => {
    const { result } = renderHook(() => useActiveThread());

    act(() => {
      result.current.beginLoadingThread('t-1');
    });

    const matchingSummary = makeSummary({
      thread_id: 't-1',
      title: 'renamed by ai',
      checkpoint_id: 'ckpt-99',
      latest_status: 'completed',
    });

    act(() => {
      result.current.applySummary(matchingSummary);
    });

    expect(result.current.activeThread.title).toBe('renamed by ai');
    expect(result.current.activeThread.checkpointId).toBe('ckpt-99');

    const otherSummary = makeSummary({ thread_id: 't-2', title: 'unrelated' });

    act(() => {
      result.current.applySummary(otherSummary);
    });

    // Slice is unchanged for non-matching summaries.
    expect(result.current.activeThread.title).toBe('renamed by ai');
  });
});
