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
  { id: 'tool-1', name: 'WebSearchTool', status: 'success', startTime: 1, endTime: 2 },
];

test('renders messages in array order and surfaces the stream-error banner when set', () => {
  // Consolidates `renders messages in array order` + `renders stream-error
  // banner when not loading` — both exercise the same MessageThreadView render
  // path with a populated message list.
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

  const renderedTexts = [
    screen.getByText('first user prompt'),
    screen.getByText('first assistant reply'),
    screen.getByText('second user prompt'),
    screen.getByText('second assistant reply'),
  ];

  for (let i = 0; i < renderedTexts.length - 1; i += 1) {
    const position = renderedTexts[i].compareDocumentPosition(renderedTexts[i + 1]);
    // Node.DOCUMENT_POSITION_FOLLOWING === 4
    expect(position & 4).toBe(4);
  }

  expect(screen.getByText('Stream failed unexpectedly')).toBeInTheDocument();
});

test('live tool overlay renders only when isHistoricalView=false', () => {
  // REGRESSION: historical-view replay must not surface live tool overlays.
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
  expect(screen.getByText(/completed websearchtool/i)).toBeInTheDocument();

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
