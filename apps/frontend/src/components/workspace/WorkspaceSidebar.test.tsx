import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

import { WorkspaceSidebar } from '@/components/workspace/WorkspaceSidebar';
import type { ThreadSummary } from '@/types/thread';

const threads: ThreadSummary[] = [
  {
    thread_id: 'thread-alpha',
    title: 'Alpha thread',
    preview: 'preview text',
    created_at: '2026-04-01T00:00:00Z',
    last_activity_at: '2026-04-01T00:01:00Z',
    message_count: 1,
    latest_status: 'completed',
    checkpoint_id: 'cp-alpha',
    pinned: false,
    archived: false,
  },
];

const baseProps = {
  threads,
  loadState: 'success' as const,
  error: '',
  activeThreadId: '',
  disabled: false,
  mobileSidebarOpen: false,
  onCloseMobileSidebar: vi.fn(),
  onCreateThread: vi.fn(),
  onSelectThread: vi.fn(),
  onRenameThread: vi.fn(),
  onTogglePinnedThread: vi.fn(),
  onDeleteThread: vi.fn(),
};

test('clicking a thread invokes onSelectThread with the thread id', async () => {
  const user = userEvent.setup();
  const onSelectThread = vi.fn();

  render(
    <WorkspaceSidebar
      {...baseProps}
      onSelectThread={onSelectThread}
    />
  );

  const threadButton = screen.getByRole('button', { name: /open thread alpha thread/i });
  await user.click(threadButton);

  expect(onSelectThread).toHaveBeenCalledWith('thread-alpha');
});

test('clicking New Chat invokes onCreateThread', async () => {
  const user = userEvent.setup();
  const onCreateThread = vi.fn();

  render(
    <WorkspaceSidebar
      {...baseProps}
      onCreateThread={onCreateThread}
    />
  );

  await user.click(screen.getByRole('button', { name: /new chat/i }));

  expect(onCreateThread).toHaveBeenCalledTimes(1);
});

test('mobile drawer renders a close button that triggers onCloseMobileSidebar', async () => {
  const user = userEvent.setup();
  const onCloseMobileSidebar = vi.fn();

  render(
    <WorkspaceSidebar
      {...baseProps}
      mobileSidebarOpen={true}
      onCloseMobileSidebar={onCloseMobileSidebar}
    />
  );

  // Backdrop close button (aria-label) is rendered when the drawer is open.
  await user.click(screen.getByRole('button', { name: /close thread sidebar/i }));
  expect(onCloseMobileSidebar).toHaveBeenCalled();
});
