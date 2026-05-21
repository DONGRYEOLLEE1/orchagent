import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { MessageThreadView } from '@/components/workspace/MessageThreadView';
import type { ChatMessage, ToolExecution } from '@/types/agent';

const baseMessages: ChatMessage[] = [
  { id: 'm1', role: 'user', content: 'first user prompt' },
  { id: 'm2', role: 'assistant', content: 'first assistant reply' },
  { id: 'm3', role: 'user', content: 'second user prompt' },
  { id: 'm4', role: 'assistant', content: 'second assistant reply' },
];

const toolExecutions: ToolExecution[] = [
  {
    id: 'tool-1',
    name: 'WebSearchTool',
    status: 'success',
    startTime: 1,
    endTime: 2,
  },
];

test('renders messages in array order with both user and assistant turns', () => {
  render(
    <MessageThreadView
      messages={baseMessages}
      detailLoadState="success"
      toolExecutions={[]}
      isHistoricalView={true}
      loading={false}
      isInterrupted={false}
      streamError=""
      currentNode=""
      onImageSelect={vi.fn()}
      onResume={vi.fn()}
    />
  );

  // Each message must be rendered exactly once.
  const renderedTexts = [
    screen.getByText('first user prompt'),
    screen.getByText('first assistant reply'),
    screen.getByText('second user prompt'),
    screen.getByText('second assistant reply'),
  ];

  // Verify document order matches the messages array order.
  for (let i = 0; i < renderedTexts.length - 1; i += 1) {
    const current = renderedTexts[i];
    const next = renderedTexts[i + 1];
    const position = current.compareDocumentPosition(next);
    // Node.DOCUMENT_POSITION_FOLLOWING === 4
    expect(position & 4).toBe(4);
  }
});

test('hides live tool overlays when isHistoricalView=true', () => {
  // Live view path: tool overlay is attached next to the latest assistant message.
  const { rerender } = render(
    <MessageThreadView
      messages={baseMessages}
      detailLoadState="success"
      toolExecutions={toolExecutions}
      isHistoricalView={false}
      loading={false}
      isInterrupted={false}
      streamError=""
      currentNode=""
      onImageSelect={vi.fn()}
      onResume={vi.fn()}
    />
  );

  // LiveToolStatusStrip emits "Completed WebSearchTool" for a successful tool with status="success".
  expect(screen.getByText(/completed websearchtool/i)).toBeInTheDocument();

  // Switching to historical view should suppress the live tool overlay even though
  // toolExecutions remain populated.
  rerender(
    <MessageThreadView
      messages={baseMessages}
      detailLoadState="success"
      toolExecutions={toolExecutions}
      isHistoricalView={true}
      loading={false}
      isInterrupted={false}
      streamError=""
      currentNode=""
      onImageSelect={vi.fn()}
      onResume={vi.fn()}
    />
  );

  expect(screen.queryByText(/completed websearchtool/i)).not.toBeInTheDocument();
});

test('renders the stream-error banner when not loading', () => {
  render(
    <MessageThreadView
      messages={baseMessages}
      detailLoadState="success"
      toolExecutions={[]}
      isHistoricalView={false}
      loading={false}
      isInterrupted={false}
      streamError="Stream failed unexpectedly"
      currentNode=""
      onImageSelect={vi.fn()}
      onResume={vi.fn()}
    />
  );

  expect(screen.getByText('Stream failed unexpectedly')).toBeInTheDocument();
});
