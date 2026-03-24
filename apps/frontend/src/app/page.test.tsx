/* eslint-disable @next/next/no-img-element */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import ChatWorkspace from '@/app/page';

const replaceMock = vi.fn();

beforeEach(() => {
  replaceMock.mockReset();
});

vi.mock('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt || ''} />,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
}));

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('remark-gfm', () => ({
  default: () => null,
}));

vi.mock('react-syntax-highlighter', () => ({
  Prism: ({ children }: { children: React.ReactNode }) => <pre>{children}</pre>,
}));

vi.mock('react-syntax-highlighter/dist/esm/styles/prism', () => ({
  atomDark: {},
}));

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function deferredSseResponse() {
  const encoder = new TextEncoder();
  let controllerRef: ReadableStreamDefaultController<Uint8Array> | null = null;
  const response = new Response(
    new ReadableStream({
      start(controller) {
        controllerRef = controller;
      },
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }
  );

  return {
    response,
    complete(payloads: unknown[]) {
      const body = payloads.map((payload) => `data: ${JSON.stringify(payload)}\n\n`).join('');
      controllerRef?.enqueue(encoder.encode(body));
      controllerRef?.close();
    },
  };
}

function defaultTelemetryPayload(threadId: string) {
  return {
    thread_id: threadId,
    reasoning_summary: '',
    suggested_queries: [],
  };
}

function maybeHandleTelemetryRequest(url: string): Response | null {
  const telemetryMatch = url.match(/\/api\/threads\/([^/]+)\/telemetry$/);
  if (telemetryMatch) {
    return jsonResponse(defaultTelemetryPayload(decodeURIComponent(telemetryMatch[1])));
  }

  const suggestionsMatch = url.match(/\/api\/threads\/([^/]+)\/suggested-queries$/);
  if (suggestionsMatch) {
    return jsonResponse(defaultTelemetryPayload(decodeURIComponent(suggestionsMatch[1])));
  }

  return null;
}

function renderWorkspace() {
  return render(
    <AuthProvider>
      <ChatWorkspace />
    </AuthProvider>
  );
}

test('hydrates a selected thread and resets to a draft with New Chat', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Existing thread',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Existing thread',
          preview: 'Saved assistant answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Saved user question',
            created_at: '2026-03-22T10:00:00Z',
          },
          {
            id: 'm-2',
            role: 'assistant',
            content: 'Saved assistant answer',
            created_at: '2026-03-22T10:01:00Z',
          },
        ],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread existing thread/i }));

  expect(await screen.findByText('Saved user question')).toBeInTheDocument();
  expect(screen.getAllByText('Saved assistant answer').length).toBeGreaterThan(0);
  expect(screen.getByText(/historical timeline replay is not restored in v1/i)).toBeInTheDocument();
  expect(screen.queryByText(/session state/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /new chat/i }));

  expect(await screen.findByText('System Ready')).toBeInTheDocument();
  expect(screen.getAllByText('draft_session').length).toBeGreaterThan(0);
});

test('hydrates historical reasoning summary and suggested queries for a selected thread', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-telemetry',
            title: 'Telemetry thread',
            preview: 'Saved answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-telemetry/telemetry')) {
      return jsonResponse({
        thread_id: 'thread-telemetry',
        reasoning_summary: '저장된 reasoning summary',
        suggested_queries: ['후속 질문 A', '후속 질문 B'],
      });
    }

    if (url.includes('/api/threads/thread-telemetry')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-telemetry',
          title: 'Telemetry thread',
          preview: 'Saved answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Saved user question',
            created_at: '2026-03-22T10:00:00Z',
          },
          {
            id: 'm-2',
            role: 'assistant',
            content: 'Saved assistant answer',
            created_at: '2026-03-22T10:01:00Z',
          },
        ],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread telemetry thread/i }));

  expect(await screen.findByText('저장된 reasoning summary')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '후속 질문 A' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '후속 질문 B' })).toBeInTheDocument();
});

test('reuses the selected thread id for follow-up sends and disables switching while streaming', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Primary thread',
            preview: 'Existing answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
          {
            thread_id: 'thread-2',
            title: 'Secondary thread',
            preview: 'Another answer',
            created_at: '2026-03-22T09:00:00Z',
            last_activity_at: '2026-03-22T09:15:00Z',
            message_count: 1,
            latest_status: 'completed',
            checkpoint_id: 'cp-2',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Primary thread',
          preview: 'Existing answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Original question',
            created_at: '2026-03-22T10:00:00Z',
          },
          {
            id: 'm-2',
            role: 'assistant',
            content: 'Existing answer',
            created_at: '2026-03-22T10:01:00Z',
          },
        ],
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      expect(body.thread_id).toBe('thread-1');
      return deferred.response;
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread primary thread/i }));
  expect(await screen.findByText('Original question')).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText(/message orchagent/i), 'Follow up request');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  expect(screen.getByRole('button', { name: /open thread secondary thread/i })).toHaveAttribute('aria-disabled', 'true');
  expect(screen.getByRole('button', { name: /new chat/i })).toBeDisabled();

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: 'thread-1',
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'text',
      node: 'assistant',
      content: 'Follow up answer',
      timestamp: '2026-03-22T10:20:01Z',
    },
    {
      event_type: 'checkpoint',
      thread_id: 'thread-1',
      checkpoint_id: 'cp-3',
      timestamp: '2026-03-22T10:20:02Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: 'thread-1',
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  await waitFor(() => {
    expect(screen.getByText('Follow up answer')).toBeInTheDocument();
  });
});

test('starts ai title generation in parallel for a new thread and patches the title before chat completion', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: generatedThreadId
          ? [
              {
                thread_id: generatedThreadId,
                title: 'RoPE 논문 탐색',
                preview: '응답 대기 중',
                created_at: '2026-03-22T10:00:00Z',
                last_activity_at: '2026-03-22T10:00:00Z',
                message_count: 1,
                latest_status: 'running',
                checkpoint_id: null,
                pinned: false,
                archived: false,
              },
            ]
          : [],
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      const match = url.match(/\/api\/threads\/([^/]+)\/ai-title$/);
      const threadId = match?.[1];
      generatedThreadId = decodeURIComponent(threadId || '');
      return jsonResponse({
        thread_id: generatedThreadId,
        title: 'RoPE 논문 탐색',
        preview: '응답 대기 중',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:00:00Z',
        message_count: 1,
        latest_status: 'running',
        checkpoint_id: null,
        pinned: false,
        archived: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  const prompt = '웹검색을 통해 RoPE 논문을 탐색하고 메인 연구자가 원하는 바는 무엇인지 설명해주세요.';
  await user.type(await screen.findByPlaceholderText(/message orchagent/i), prompt);
  await user.click(screen.getByRole('button', { name: /send message/i }));

  await waitFor(() => {
    expect(screen.getAllByText('RoPE 논문 탐색').length).toBeGreaterThan(0);
  });

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: generatedThreadId,
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'text',
      node: 'assistant',
      content: '최종 응답',
      timestamp: '2026-03-22T10:20:01Z',
    },
    {
      event_type: 'checkpoint',
      thread_id: generatedThreadId,
      checkpoint_id: 'cp-1',
      timestamp: '2026-03-22T10:20:02Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  await waitFor(() => {
    expect(screen.getByText('최종 응답')).toBeInTheDocument();
  });

  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/api/chat'))).toBe(true);
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/ai-title'))).toBe(true);
});

test('generates suggested queries after a completed answer and injects the clicked prompt', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse({
        thread_id: generatedThreadId,
        title: 'RoPE 논문 탐색',
        preview: '응답 대기 중',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:00:00Z',
        message_count: 1,
        latest_status: 'running',
        checkpoint_id: null,
        pinned: false,
        archived: false,
      });
    }

    if (url.endsWith('/suggested-queries')) {
      return jsonResponse({
        thread_id: generatedThreadId,
        reasoning_summary: 'live reasoning',
        suggested_queries: ['RoPE와 ALiBi 차이도 비교해줘'],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.type(await screen.findByPlaceholderText(/message orchagent/i), 'RoPE 논문 설명해줘');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/suggested-queries'))).toBe(false);

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: generatedThreadId,
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'text',
      node: 'assistant',
      content: '최종 응답',
      timestamp: '2026-03-22T10:20:01Z',
    },
    {
      event_type: 'checkpoint',
      thread_id: generatedThreadId,
      checkpoint_id: 'cp-1',
      timestamp: '2026-03-22T10:20:02Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  const suggestionButton = await screen.findByRole('button', {
    name: 'RoPE와 ALiBi 차이도 비교해줘',
  });
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/suggested-queries'))).toBe(true);

  await user.click(suggestionButton);
  expect(screen.getByDisplayValue('RoPE와 ALiBi 차이도 비교해줘')).toBeInTheDocument();
});

test('streams reasoning summary content into the inner monologue panel', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse({
        thread_id: generatedThreadId,
        title: 'reasoning 테스트',
        preview: '응답 대기 중',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:00:00Z',
        message_count: 1,
        latest_status: 'running',
        checkpoint_id: null,
        pinned: false,
        archived: false,
      });
    }

    if (url.endsWith('/suggested-queries')) {
      return jsonResponse(defaultTelemetryPayload(generatedThreadId));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.type(await screen.findByPlaceholderText(/message orchagent/i), 'reasoning 테스트');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  deferred.complete([
    {
      event_type: 'reasoning',
      node: 'head_supervisor',
      content: '이 turn은 research보다 synthesis가 먼저 필요하다.',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  expect(await screen.findByText(/research보다 synthesis가 먼저 필요하다/i)).toBeInTheDocument();
});

test('shows a live fallback summary when no reasoning chunk is streamed', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse({
        thread_id: generatedThreadId,
        title: '작업 파일 생성',
        preview: '응답 대기 중',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:00:00Z',
        message_count: 1,
        latest_status: 'running',
        checkpoint_id: null,
        pinned: false,
        archived: false,
      });
    }

    if (url.endsWith('/suggested-queries')) {
      return jsonResponse(defaultTelemetryPayload(generatedThreadId));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.type(await screen.findByPlaceholderText(/message orchagent/i), 'Create a file named hi.txt in the workspace and write hi into it.');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  deferred.complete([
    {
      event_type: 'tool_start',
      node: 'filesystem_write',
      tool_name: 'filesystem_write',
      display_name: 'Filesystem Write',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'status',
      status: 'running',
      thread_id: generatedThreadId,
      node: 'writing_team',
      display_name: 'Writing Team',
      timestamp: '2026-03-22T10:20:01Z',
    },
  ]);

  expect(await screen.findByText(/Filesystem Write 도구 결과를 바탕으로 응답 근거를 정리하는 중입니다/i)).toBeInTheDocument();
});

test('keeps a manual rename when a delayed ai title response arrives later', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';
  let resolveAiTitle: ((response: Response) => void) | null = null;

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return Promise.resolve(telemetryResponse);
    }

    if (url.includes('/api/auth/me')) {
      return Promise.resolve(jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      }));
    }

    if (url.includes('/api/threads?limit=50')) {
      return Promise.resolve(jsonResponse({
        threads: generatedThreadId
          ? [
              {
                thread_id: generatedThreadId,
                title: '웹검색을 통해 ALiBi 위치 인코딩을 조사하고 500자 내외로 설명해줘.',
                preview: '응답 대기 중',
                created_at: '2026-03-22T10:00:00Z',
                last_activity_at: '2026-03-22T10:00:00Z',
                message_count: 1,
                latest_status: 'running',
                checkpoint_id: null,
                pinned: false,
                archived: false,
              },
            ]
          : [],
      }));
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return Promise.resolve(deferred.response);
    }

    if (url.endsWith('/ai-title')) {
      const match = url.match(/\/api\/threads\/([^/]+)\/ai-title$/);
      generatedThreadId = decodeURIComponent(match?.[1] || '');
      return new Promise<Response>((resolve) => {
        resolveAiTitle = resolve;
      });
    }

    if (url.includes(`/api/threads/${generatedThreadId}`) && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body || '{}'));
      return Promise.resolve(jsonResponse({
        thread_id: generatedThreadId,
        title: body.title || '수동 제목',
        preview: '응답 대기 중',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:15:00Z',
        message_count: 1,
        latest_status: 'completed',
        checkpoint_id: 'cp-1',
        pinned: body.pinned ?? false,
        archived: false,
      }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.type(
    await screen.findByPlaceholderText(/message orchagent/i),
    '웹검색을 통해 ALiBi 위치 인코딩을 조사하고 500자 내외로 설명해줘.'
  );
  await user.click(screen.getByRole('button', { name: /send message/i }));

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: generatedThreadId,
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'text',
      node: 'assistant',
      content: '응답 완료',
      timestamp: '2026-03-22T10:20:01Z',
    },
    {
      event_type: 'checkpoint',
      thread_id: generatedThreadId,
      checkpoint_id: 'cp-1',
      timestamp: '2026-03-22T10:20:02Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  await waitFor(() => {
    expect(screen.getByText('응답 완료')).toBeInTheDocument();
  });

  const createdThreadButton = screen.getAllByRole('button', { name: /open thread/i })[0];
  await user.hover(createdThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions/i }));
  await user.click(screen.getByRole('button', { name: /rename/i }));

  const renameInput = screen.getByLabelText(new RegExp(`rename thread ${generatedThreadId}`, 'i'));
  await user.clear(renameInput);
  await user.type(renameInput, '수동 제목');
  fireEvent.blur(renameInput);

  await waitFor(() => {
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes(`/api/threads/${generatedThreadId}`) && init?.method === 'PATCH')).toBe(true);
  });

  resolveAiTitle?.(jsonResponse({
    thread_id: generatedThreadId,
    title: 'AI 제목',
    preview: '응답 대기 중',
    created_at: '2026-03-22T10:00:00Z',
    last_activity_at: '2026-03-22T10:00:00Z',
    message_count: 1,
    latest_status: 'running',
    checkpoint_id: null,
    pinned: false,
    archived: false,
  }));

  await waitFor(() => {
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes(`/api/threads/${generatedThreadId}`) && init?.method === 'PATCH')).toBe(true);
  });
  expect(screen.queryByText('AI 제목')).not.toBeInTheDocument();
});

test('keeps the optimistic fallback title when ai title generation fails', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';
  const prompt = '이 질문은 fallback 제목이 유지되는지 확인하기 위한 매우 긴 테스트 메시지입니다.';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse({ detail: 'title failed' }, 500);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.type(await screen.findByPlaceholderText(/message orchagent/i), prompt);
  await user.click(screen.getByRole('button', { name: /send message/i }));

  const fallbackTitle = prompt;
  await waitFor(() => {
    expect(screen.getAllByText(fallbackTitle).length).toBeGreaterThan(0);
  });

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: generatedThreadId,
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    {
      event_type: 'text',
      node: 'assistant',
      content: 'fallback 응답',
      timestamp: '2026-03-22T10:20:01Z',
    },
    {
      event_type: 'checkpoint',
      thread_id: generatedThreadId,
      checkpoint_id: 'cp-1',
      timestamp: '2026-03-22T10:20:02Z',
    },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  await waitFor(() => {
    expect(screen.getByText('fallback 응답')).toBeInTheDocument();
  });
  expect(screen.queryByText('AI 제목')).not.toBeInTheDocument();
});

test('marks a thread as errored when a send request fails before streaming starts', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Primary thread',
            preview: 'Existing answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Primary thread',
          preview: 'Existing answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Original question',
            created_at: '2026-03-22T10:00:00Z',
          },
          {
            id: 'm-2',
            role: 'assistant',
            content: 'Existing answer',
            created_at: '2026-03-22T10:01:00Z',
          },
        ],
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      expect(body.thread_id).toBe('thread-1');
      return jsonResponse({ detail: 'Backend exploded' }, 500);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread primary thread/i }));
  await user.type(screen.getByPlaceholderText(/message orchagent/i), 'Failing follow up');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  await waitFor(() => {
    expect(screen.getByText('Backend exploded')).toBeInTheDocument();
  });

  expect(screen.getAllByText('Errored').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: /open thread primary thread/i })).toBeEnabled();
});

test('restores interrupted resume state when resume fails before streaming starts', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Interrupted thread',
            preview: 'Awaiting approval',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'interrupted',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Interrupted thread',
          preview: 'Awaiting approval',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'interrupted',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Do the risky thing',
            created_at: '2026-03-22T10:00:00Z',
          },
          {
            id: 'm-2',
            role: 'assistant',
            content: 'Awaiting approval',
            created_at: '2026-03-22T10:01:00Z',
          },
        ],
      });
    }

    if (url.endsWith('/api/chat/resume')) {
      return jsonResponse({ detail: 'Resume failed' }, 500);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread interrupted thread/i }));
  expect(await screen.findByText(/action required/i)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /approve & continue/i }));

  await waitFor(() => {
    expect(screen.getByText('Resume failed')).toBeInTheDocument();
  });

  expect(screen.getByText(/action required/i)).toBeInTheDocument();
  expect(screen.queryByText(/\[User Action\]: approve/i)).not.toBeInTheDocument();
});

test('renames and pins a thread optimistically', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Existing thread',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1')) {
      if (init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body || '{}'));
        return jsonResponse({
          thread_id: 'thread-1',
          title: body.title || 'Existing thread',
          preview: 'Saved assistant answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: body.pinned ?? false,
          archived: false,
        });
      }

      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Existing thread',
          preview: 'Saved assistant answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  const existingThreadButton = await screen.findByRole('button', { name: /open thread existing thread/i });
  await user.hover(existingThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions existing thread/i }));
  await user.click(screen.getByRole('button', { name: /rename existing thread/i }));
  const renameInput = screen.getByLabelText(/rename thread thread-1/i);
  await user.clear(renameInput);
  await user.type(renameInput, 'Renamed thread');
  fireEvent.blur(renameInput);

  await waitFor(() => {
    const patchCalls = fetchMock.mock.calls.filter(([input, init]) => {
      const url = String(input);
      return url.endsWith('/api/threads/thread-1') && init?.method === 'PATCH';
    });
    expect(patchCalls.length).toBeGreaterThan(0);
  });

  await user.click(screen.getByRole('button', { name: /thread actions/i }));
  await user.click(screen.getByRole('button', { name: /pin/i }));
  expect(await screen.findByText('Pinned')).toBeInTheDocument();
});

test('toggles a thread pin state independently', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-2',
            title: 'Already top',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T11:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-2',
            pinned: false,
            archived: false,
          },
          {
            thread_id: 'thread-1',
            title: 'Pin me',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1')) {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse({
        thread_id: 'thread-1',
        title: 'Pin me',
        preview: 'Saved assistant answer',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:15:00Z',
        message_count: 2,
        latest_status: 'completed',
        checkpoint_id: 'cp-1',
        pinned: body.pinned ?? false,
        archived: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  expect(
    (await screen.findAllByRole('button', { name: /open thread/i })).map((button) => button.getAttribute('aria-label'))
  ).toEqual([
    'Open thread Already top',
    'Open thread Pin me',
  ]);

  const pinThreadButton = await screen.findByRole('button', { name: /open thread pin me/i });
  await user.hover(pinThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions pin me/i }));
  await user.click(screen.getByRole('button', { name: /pin pin me/i }));
  expect(await screen.findByText('Pinned')).toBeInTheDocument();
  expect(
    screen.getAllByRole('button', { name: /open thread/i }).map((button) => button.getAttribute('aria-label'))
  ).toEqual([
    'Open thread Pin me',
    'Open thread Already top',
  ]);
});

test('returns an unpinned thread to activity order after unpin', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Pinned now',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: true,
            archived: false,
          },
          {
            thread_id: 'thread-2',
            title: 'Newer thread',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T11:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-2',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1')) {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse({
        thread_id: 'thread-1',
        title: 'Pinned now',
        preview: 'Saved assistant answer',
        created_at: '2026-03-22T10:00:00Z',
        last_activity_at: '2026-03-22T10:15:00Z',
        message_count: 2,
        latest_status: 'completed',
        checkpoint_id: 'cp-1',
        pinned: body.pinned ?? true,
        archived: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  expect(
    (await screen.findAllByRole('button', { name: /open thread/i })).map((button) => button.getAttribute('aria-label'))
  ).toEqual([
    'Open thread Pinned now',
    'Open thread Newer thread',
  ]);

  const pinnedThreadButton = await screen.findByRole('button', { name: /open thread pinned now/i });
  await user.hover(pinnedThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions pinned now/i }));
  await user.click(screen.getByRole('button', { name: /unpin pinned now/i }));

  expect(
    screen.getAllByRole('button', { name: /open thread/i }).map((button) => button.getAttribute('aria-label'))
  ).toEqual([
    'Open thread Newer thread',
    'Open thread Pinned now',
  ]);
});

test('deletes a thread and returns to draft when the active thread is removed', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) {
      return telemetryResponse;
    }

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          {
            thread_id: 'thread-1',
            title: 'Delete me',
            preview: 'Saved assistant answer',
            created_at: '2026-03-22T10:00:00Z',
            last_activity_at: '2026-03-22T10:15:00Z',
            message_count: 2,
            latest_status: 'completed',
            checkpoint_id: 'cp-1',
            pinned: false,
            archived: false,
          },
        ],
      });
    }

    if (url.includes('/api/threads/thread-1') && (!init || init.method === 'GET')) {
      return jsonResponse({
        thread: {
          thread_id: 'thread-1',
          title: 'Delete me',
          preview: 'Saved assistant answer',
          created_at: '2026-03-22T10:00:00Z',
          last_activity_at: '2026-03-22T10:15:00Z',
          message_count: 2,
          latest_status: 'completed',
          checkpoint_id: 'cp-1',
          pinned: false,
          archived: false,
        },
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Delete this thread',
            created_at: '2026-03-22T10:00:00Z',
          },
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1') && init?.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread delete me/i }));
  expect(await screen.findByText('Delete this thread')).toBeInTheDocument();

  const deleteThreadButton = screen.getByRole('button', { name: /open thread delete me/i });
  await user.hover(deleteThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions delete me/i }));
  await user.click(screen.getByRole('button', { name: /delete delete me/i }));

  expect(await screen.findByText('System Ready')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /open thread delete me/i })).not.toBeInTheDocument();
});
