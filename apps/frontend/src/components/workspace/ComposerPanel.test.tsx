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
  const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
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

  await user.keyboard('{Enter}');
  expect(onSubmit).toHaveBeenCalledTimes(1);

  onSubmit.mockClear();
  await user.keyboard('{Shift>}{Enter}{/Shift}');
  expect(onSubmit).not.toHaveBeenCalled();
  expect(onInputChange).toHaveBeenCalled();
});

test('Send button enabled state reflects input + lock + attachment props', () => {
  // Consolidates three prior state-permutation cases:
  // empty + no attachments → disabled
  // input present → enabled
  // interaction locked → disabled (and textarea/add-files also locked)
  const { rerender } = render(
    <ComposerPanel {...defaultProps} input="" hasSendableAttachments={false} />
  );
  expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();

  rerender(<ComposerPanel {...defaultProps} input="non-empty" />);
  expect(screen.getByRole('button', { name: /send message/i })).not.toBeDisabled();

  rerender(<ComposerPanel {...defaultProps} input="ready to send" isInteractionLocked={true} />);
  expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /add files/i })).toBeDisabled();
  expect(screen.getByPlaceholderText(/message orchagent/i)).toBeDisabled();
});
