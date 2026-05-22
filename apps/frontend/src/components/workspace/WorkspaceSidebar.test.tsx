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

test('desktop sidebar forwards thread selection + new-chat clicks', async () => {
  // Consolidates `clicking a thread invokes onSelectThread` +
  // `clicking New Chat invokes onCreateThread` (both fire from the desktop
  // sidebar layout).
  const user = userEvent.setup();
  const onSelectThread = vi.fn();
  const onCreateThread = vi.fn();

  render(
    <WorkspaceSidebar
      {...baseProps}
      onSelectThread={onSelectThread}
      onCreateThread={onCreateThread}
    />
  );

  await user.click(screen.getByRole('button', { name: /open thread alpha thread/i }));
  expect(onSelectThread).toHaveBeenCalledWith('thread-alpha');

  await user.click(screen.getByRole('button', { name: /new chat/i }));
  expect(onCreateThread).toHaveBeenCalledTimes(1);
});

test('mobile drawer renders a close button that triggers onCloseMobileSidebar', async () => {
  // Kept separate from the desktop test — mobile mode mounts a second drawer
  // that duplicates buttons, so a dedicated render isolates the close-button
  // hookup unambiguously.
  const user = userEvent.setup();
  const onCloseMobileSidebar = vi.fn();

  render(
    <WorkspaceSidebar
      {...baseProps}
      mobileSidebarOpen={true}
      onCloseMobileSidebar={onCloseMobileSidebar}
    />
  );

  await user.click(screen.getByRole('button', { name: /close thread sidebar/i }));
  expect(onCloseMobileSidebar).toHaveBeenCalled();
});
