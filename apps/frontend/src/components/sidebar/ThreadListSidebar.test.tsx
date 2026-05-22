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

test('thread row click, action menu open + delete, and backdrop close all fire the right callbacks', async () => {
  // Consolidates `renders saved thread items and forwards selection` +
  // `closes the thread actions menu when the backdrop is clicked`.
  const user = userEvent.setup();
  const onSelectThread = vi.fn();
  const onDeleteThread = vi.fn();

  render(
    <ThreadListSidebar
      threads={threads}
      loadState="success"
      error=""
      selectedThreadId=""
      disabled={false}
      onNewChat={vi.fn()}
      onSelectThread={onSelectThread}
      onDeleteThread={onDeleteThread}
    />
  );

  const threadButton = screen.getByRole('button', { name: /open thread first thread/i });
  await user.hover(threadButton);
  await user.click(threadButton);
  expect(onSelectThread).toHaveBeenCalledWith('thread-1');

  await user.click(screen.getByRole('button', { name: /thread actions first thread/i }));
  expect(screen.getByRole('menu')).toBeInTheDocument();

  // Backdrop close still works without firing delete.
  await user.click(screen.getByRole('button', { name: /close thread actions menu for first thread/i }));
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();

  // Re-open and confirm delete still routes through onDeleteThread.
  await user.hover(threadButton);
  await user.click(screen.getByRole('button', { name: /thread actions first thread/i }));
  await user.click(screen.getByRole('button', { name: /delete first thread/i }));
  expect(onDeleteThread).toHaveBeenCalledWith('thread-1');
});

test('renders empty + loading + error + disabled states', () => {
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
