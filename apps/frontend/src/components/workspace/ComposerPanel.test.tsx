import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

import { ComposerPanel } from '@/components/workspace/ComposerPanel';

const defaultProps = {
  input: '',
  onInputChange: vi.fn(),
  selectedFiles: [],
  selectedFileStatuses: {},
  attachmentUploadState: 'idle' as const,
  attachmentError: '',
  onAttachmentChange: vi.fn(),
  onRemoveAttachment: vi.fn(),
  onSubmit: vi.fn((event: React.FormEvent) => {
    event.preventDefault();
  }),
  isInteractionLocked: false,
  loading: false,
  hasSendableAttachments: false,
  repoBinding: null,
  repoBindingLoading: false,
  repoBindingError: '',
  onBindRepositoryUrl: vi.fn(),
  onBindRepositoryZip: vi.fn(),
  onDeleteRepositoryBinding: vi.fn(),
  onMaterializeRepository: vi.fn(),
};

test('Enter submits the form and Shift+Enter inserts a newline', async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn((event: React.FormEvent) => {
    event.preventDefault();
  });
  const onInputChange = vi.fn();

  render(
    <ComposerPanel
      {...defaultProps}
      input="hello"
      onInputChange={onInputChange}
      onSubmit={onSubmit}
    />
  );

  const textarea = screen.getByPlaceholderText(/message orchagent/i);
  textarea.focus();

  // Enter (without Shift) requests submit.
  await user.keyboard('{Enter}');
  expect(onSubmit).toHaveBeenCalledTimes(1);

  // Shift+Enter does NOT call submit; it should pass through to default textarea
  // behavior. userEvent will dispatch the key without our preventDefault stopping it.
  onSubmit.mockClear();
  await user.keyboard('{Shift>}{Enter}{/Shift}');
  expect(onSubmit).not.toHaveBeenCalled();
  // The Shift+Enter keystroke is forwarded to the textarea, producing a change event
  // with a newline. userEvent will route the keystroke through onChange because we
  // don't preventDefault for Shift+Enter.
  expect(onInputChange).toHaveBeenCalled();
});

test('Send button is disabled while interaction is locked', () => {
  render(
    <ComposerPanel
      {...defaultProps}
      input="ready to send"
      isInteractionLocked={true}
    />
  );

  const sendButton = screen.getByRole('button', { name: /send message/i });
  expect(sendButton).toBeDisabled();

  // Add files button and textarea should also be disabled while locked.
  expect(screen.getByRole('button', { name: /add files/i })).toBeDisabled();
  expect(screen.getByPlaceholderText(/message orchagent/i)).toBeDisabled();
});

test('Send button is disabled when input is empty and no sendable attachments', () => {
  render(
    <ComposerPanel
      {...defaultProps}
      input=""
      hasSendableAttachments={false}
    />
  );

  expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
});

test('Send button enables when input has content', () => {
  render(<ComposerPanel {...defaultProps} input="non-empty" />);

  expect(screen.getByRole('button', { name: /send message/i })).not.toBeDisabled();
});
