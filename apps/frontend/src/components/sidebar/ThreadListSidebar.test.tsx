import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

import { ThreadListSidebar } from '@/components/sidebar/ThreadListSidebar';
import type { ThreadSummary } from '@/types/thread';

const threads: ThreadSummary[] = [
  {
    thread_id: 'thread-1',
    title: 'First thread',
    preview: 'A saved preview',
    created_at: '2026-03-22T10:00:00Z',
    last_activity_at: '2026-03-22T10:05:00Z',
    message_count: 2,
    latest_status: 'completed',
    checkpoint_id: 'cp-1',
    pinned: false,
    archived: false,
  },
];

test('renders saved thread items and forwards selection', async () => {
  const user = userEvent.setup();
  const onSelectThread = vi.fn();
  const onNewChat = vi.fn();
  const onDeleteThread = vi.fn();

  render(
    <ThreadListSidebar
      threads={threads}
      loadState="success"
      error=""
      selectedThreadId=""
      disabled={false}
      onNewChat={onNewChat}
      onSelectThread={onSelectThread}
      onDeleteThread={onDeleteThread}
    />
  );

  await user.click(screen.getByRole('button', { name: /open thread first thread/i }));
  await user.click(screen.getByRole('button', { name: /delete first thread/i }));

  expect(screen.getByText('First thread')).toBeInTheDocument();
  expect(screen.getByText('A saved preview')).toBeInTheDocument();
  expect(onSelectThread).toHaveBeenCalledWith('thread-1');
  expect(onDeleteThread).toHaveBeenCalledWith('thread-1');
});

test('shows empty, loading, and disabled states', () => {
  const { rerender } = render(
    <ThreadListSidebar
      threads={[]}
      loadState="loading"
      error=""
      selectedThreadId=""
      disabled={false}
      onNewChat={vi.fn()}
      onSelectThread={vi.fn()}
    />
  );

  expect(screen.getByText(/loading threads/i)).toBeInTheDocument();

  rerender(
    <ThreadListSidebar
      threads={[]}
      loadState="success"
      error="Failed to load threads"
      selectedThreadId=""
      disabled={true}
      onNewChat={vi.fn()}
      onSelectThread={vi.fn()}
    />
  );

  expect(screen.getByText(/no saved threads yet/i)).toBeInTheDocument();
  expect(screen.getByText(/failed to load threads/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /new chat/i })).toBeDisabled();
});
