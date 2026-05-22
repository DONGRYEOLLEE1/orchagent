/* eslint-disable @next/next/no-img-element */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import ChatWorkspace from '@/components/workspace/WorkspaceRouteRoot';

// ---- next/navigation mocks ----

const pathnameSubscribers = new Set<() => void>();
let mockPathname = '/';

function setMockPathname(nextPath: string) {
  mockPathname = nextPath;
  pathnameSubscribers.forEach((callback) => callback());
}

const replaceMock = vi.fn((nextPath: string) => setMockPathname(nextPath));
const pushMock = vi.fn((nextPath: string) => setMockPathname(nextPath));

beforeEach(() => {
  replaceMock.mockReset();
  pushMock.mockReset();
  pathnameSubscribers.clear();
  mockPathname = '/';
  replaceMock.mockImplementation((nextPath: string) => setMockPathname(nextPath));
  pushMock.mockImplementation((nextPath: string) => setMockPathname(nextPath));
});

vi.mock('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt || ''} />,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: pushMock,
  }),
  usePathname: () => {
    const [pathname, setPathname] = React.useState(mockPathname);

    React.useEffect(() => {
      const sync = () => setPathname(mockPathname);
      pathnameSubscribers.add(sync);
      return () => {
        pathnameSubscribers.delete(sync);
      };
    }, []);

    return pathname;
  },
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

// ---- helpers ----

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

function authMePayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'user-1',
    login_id: 'tester',
    role: 'user',
    status: 'active',
    display_name: null,
    email: null,
    must_change_password: false,
    ...overrides,
  };
}

function summary(overrides: Partial<Record<string, unknown>> & { thread_id: string; title: string }) {
  return {
    preview: 'preview',
    created_at: '2026-03-22T10:00:00Z',
    last_activity_at: '2026-03-22T10:15:00Z',
    message_count: 2,
    latest_status: 'completed',
    checkpoint_id: 'cp-1',
    pinned: false,
    archived: false,
    ...overrides,
  };
}

function defaultTelemetryPayload(threadId: string) {
  return { thread_id: threadId, reasoning_summary: '', suggested_queries: [] };
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

function stubCsrfCookie() {
  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
}

function renderWorkspace(pathname = '/') {
  mockPathname = pathname;
  return render(
    <AuthProvider>
      <ChatWorkspace />
    </AuthProvider>
  );
}

// ---- tests ----

test('hydrates a selected thread (with telemetry) and resets to draft via New Chat', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [summary({ thread_id: 'thread-1', title: 'Existing thread', preview: 'Saved assistant answer' })],
      });
    }

    if (url.includes('/api/threads/thread-1/telemetry')) {
      return jsonResponse({
        thread_id: 'thread-1',
        reasoning_summary: '저장된 reasoning summary',
        suggested_queries: ['후속 질문 A'],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: summary({ thread_id: 'thread-1', title: 'Existing thread', preview: 'Saved assistant answer' }),
        messages: [
          {
            id: 'm-1',
            role: 'user',
            content: 'Saved user question',
            created_at: '2026-03-22T10:00:00Z',
            attachments: [
              {
                kind: 'image',
                url: 'http://localhost:8002/api/threads/thread-1/messages/m-1/attachments/0',
                alt: '첨부 이미지 1',
              },
            ],
          },
          { id: 'm-2', role: 'assistant', content: 'Saved assistant answer', created_at: '2026-03-22T10:01:00Z' },
        ],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread existing thread/i }));
  expect(pushMock).toHaveBeenCalledWith('/c/thread-1');

  expect(await screen.findByText('Saved user question')).toBeInTheDocument();
  expect(screen.getByAltText('첨부 이미지 1')).toBeInTheDocument();
  expect(screen.getAllByText('Saved assistant answer').length).toBeGreaterThan(0);
  expect(await screen.findByText('저장된 reasoning summary')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '후속 질문 A' })).toBeInTheDocument();

  // image preview dialog opens & closes
  await user.click(screen.getByRole('button', { name: '첨부 이미지 1 크게 보기' }));
  expect(screen.getByRole('dialog', { name: '첨부 이미지 1 확대 보기' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Close image preview' }));
  await waitFor(() => {
    expect(screen.queryByRole('dialog', { name: '첨부 이미지 1 확대 보기' })).not.toBeInTheDocument();
  });

  // new chat resets to draft
  await user.click(screen.getByRole('button', { name: /new chat/i }));
  expect(pushMock).toHaveBeenCalledWith('/');
  expect(await screen.findByText('System Ready')).toBeInTheDocument();
});

test('routes to dashboard from the top navigation', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });
    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: 'Dashboard' }));
  expect(pushMock).toHaveBeenCalledWith('/dashboard');
});

test('uploads supported files before sending chat and forwards attachment ids — assistant attachment renders post-stream', async () => {
  // REGRESSION: trend.png attachment timing (PR #8/#15) — assistant attachment
  // must appear once SSE `attachments` event is delivered.
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/uploads')) {
      expect(init?.method).toBe('POST');
      return jsonResponse({
        uploads: [
          {
            id: 'upload-1',
            kind: 'csv',
            file_name: 'sales.csv',
            mime_type: 'text/csv',
            size_bytes: 12,
            created_at: '2026-03-22T10:00:00Z',
          },
        ],
        errors: [],
        accepted_count: 1,
        failed_count: 0,
        total_size_bytes: 12,
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      expect(body.attachment_ids).toEqual(['upload-1']);
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse(summary({ thread_id: 'thread-uploaded', title: 'CSV 분석', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await screen.findByPlaceholderText(/message orchagent/i);
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement | null;
  expect(fileInput).not.toBeNull();
  const csvFile = new File(['a,b\n1,2\n'], 'sales.csv', { type: 'text/csv' });

  fireEvent.change(fileInput as HTMLInputElement, { target: { files: [csvFile] } });
  expect(await screen.findByText('sales.csv')).toBeInTheDocument();

  await user.type(screen.getByPlaceholderText(/message orchagent/i), '이 매출 파일 분석해줘');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: 'thread-uploaded',
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    { event_type: 'text', node: 'assistant', content: 'CSV 분석 시작', timestamp: '2026-03-22T10:20:01Z' },
    {
      event_type: 'attachments',
      role: 'assistant',
      message_id: 'assistant-db-id',
      attachments: [
        {
          kind: 'artifact',
          url: 'http://localhost:8002/api/threads/thread-uploaded/messages/assistant-db-id/attachments/0',
          alt: 'trend.png',
          file_name: 'trend.png',
          mime_type: 'image/png',
          size_bytes: 1200,
        },
      ],
      timestamp: '2026-03-22T10:20:01Z',
    },
    { event_type: 'checkpoint', thread_id: 'thread-uploaded', checkpoint_id: 'cp-upload', timestamp: '2026-03-22T10:20:02Z' },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: 'thread-uploaded',
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  await waitFor(() => {
    expect(screen.getByText('CSV 분석 시작')).toBeInTheDocument();
  });
  await waitFor(
    () => {
      expect(screen.getByAltText('trend.png')).toBeInTheDocument();
    },
    { timeout: 10000 },
  );

  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/api/uploads'))).toBe(true);
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/api/chat'))).toBe(true);
});

test('blocks selecting more than five files and keeps the first five in the tray', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });
    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await screen.findByPlaceholderText(/message orchagent/i);
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  const files = Array.from({ length: 6 }, (_, index) =>
    new File([`{"index":${index}}`], `sample-${index}.json`, { type: 'application/json' })
  );

  fireEvent.change(fileInput, { target: { files } });

  expect(await screen.findByText(/한 번에 최대 5개 파일만 첨부할 수 있습니다/i)).toBeInTheDocument();
  expect(screen.getByText('sample-0.json')).toBeInTheDocument();
  expect(screen.getByText('sample-4.json')).toBeInTheDocument();
  expect(screen.queryByText('sample-5.json')).not.toBeInTheDocument();
});

test('partial upload keeps failed files in the tray while the accepted file still streams', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/uploads')) {
      return jsonResponse({
        uploads: [
          {
            id: 'upload-json',
            input_index: 0,
            kind: 'json',
            file_name: 'keep.json',
            mime_type: 'application/json',
            size_bytes: 12,
            created_at: '2026-03-22T10:00:00Z',
          },
        ],
        errors: [
          {
            input_index: 1,
            file_name: 'reject.csv',
            error_code: 'file_too_large',
            detail: 'CSV file exceeds 10MB limit',
          },
        ],
        accepted_count: 1,
        failed_count: 1,
        total_size_bytes: 12,
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      expect(body.attachment_ids).toEqual(['upload-json']);
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse(summary({ thread_id: 'thread-partial', title: '부분 업로드', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await screen.findByPlaceholderText(/message orchagent/i);
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(fileInput, {
    target: {
      files: [
        new File(['{"ok":1}'], 'keep.json', { type: 'application/json' }),
        new File(['a,b\n1,2\n'], 'reject.csv', { type: 'text/csv' }),
      ],
    },
  });

  await user.type(screen.getByPlaceholderText(/message orchagent/i), '부분 업로드 테스트');
  await user.click(screen.getByRole('button', { name: /send message/i }));

  deferred.complete([
    {
      event_type: 'status',
      status: 'running',
      thread_id: 'thread-partial',
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      timestamp: '2026-03-22T10:20:00Z',
    },
    { event_type: 'text', node: 'assistant', content: '부분 업로드 응답', timestamp: '2026-03-22T10:20:01Z' },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: 'thread-partial',
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  expect(await screen.findByText(/reject.csv: CSV file exceeds 10MB limit/i)).toBeInTheDocument();
  await waitFor(
    () => {
      expect(screen.queryByText((content) => content.includes('부분 업로드 응답'))).not.toBeNull();
    },
    { timeout: 10000 },
  );
});

test('follow-up sends reuse the selected thread id and disable sidebar switching while streaming', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          summary({ thread_id: 'thread-1', title: 'Primary thread', preview: 'Existing answer' }),
          summary({ thread_id: 'thread-2', title: 'Secondary thread', preview: 'Another answer', message_count: 1, last_activity_at: '2026-03-22T09:15:00Z' }),
        ],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: summary({ thread_id: 'thread-1', title: 'Primary thread', preview: 'Existing answer' }),
        messages: [
          { id: 'm-1', role: 'user', content: 'Original question', created_at: '2026-03-22T10:00:00Z' },
          { id: 'm-2', role: 'assistant', content: 'Existing answer', created_at: '2026-03-22T10:01:00Z' },
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
    { event_type: 'text', node: 'assistant', content: 'Follow up answer', timestamp: '2026-03-22T10:20:01Z' },
    { event_type: 'checkpoint', thread_id: 'thread-1', checkpoint_id: 'cp-3', timestamp: '2026-03-22T10:20:02Z' },
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

test('ai title patches the optimistic thread on success and falls back to the prompt on failure', async () => {
  // Consolidates two prior cases: parallel ai-title success + ai-title failure
  // both checked from one render via two distinct fetch flows would be hard,
  // so we run two minimal scenarios sequentially in one test by swapping
  // the fetch mock between sub-scenarios.
  const successDeferred = deferredSseResponse();
  let generatedThreadId = '';

  const successFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: generatedThreadId
          ? [summary({ thread_id: generatedThreadId, title: 'RoPE 논문 탐색', latest_status: 'running', checkpoint_id: null, message_count: 1 })]
          : [],
      });
    }

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return successDeferred.response;
    }

    if (url.endsWith('/ai-title')) {
      const match = url.match(/\/api\/threads\/([^/]+)\/ai-title$/);
      generatedThreadId = decodeURIComponent(match?.[1] || generatedThreadId);
      return jsonResponse(summary({ thread_id: generatedThreadId, title: 'RoPE 논문 탐색', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', successFetch);

  const userOne = userEvent.setup();
  const { unmount } = renderWorkspace();

  await userOne.type(await screen.findByPlaceholderText(/message orchagent/i), 'RoPE 논문 탐색해줘');
  await userOne.click(screen.getByRole('button', { name: /send message/i }));

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith(`/c/${generatedThreadId}`);
  });

  await waitFor(() => {
    expect(screen.getAllByText('RoPE 논문 탐색').length).toBeGreaterThan(0);
  });

  successDeferred.complete([
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  unmount();

  // Sub-scenario 2: ai-title failure keeps the optimistic fallback title.
  const failureDeferred = deferredSseResponse();
  let failureThreadId = '';
  const failurePrompt = '이 질문은 fallback 제목이 유지되는지 확인하기 위한 매우 긴 테스트 메시지입니다.';

  const failureFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      failureThreadId = body.thread_id;
      return failureDeferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse({ detail: 'title failed' }, 500);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', failureFetch);

  const userTwo = userEvent.setup();
  renderWorkspace();

  await userTwo.type(await screen.findByPlaceholderText(/message orchagent/i), failurePrompt);
  await userTwo.click(screen.getByRole('button', { name: /send message/i }));

  await waitFor(() => {
    expect(screen.getAllByText(failurePrompt).length).toBeGreaterThan(0);
  });

  failureDeferred.complete([
    {
      event_type: 'status',
      status: 'completed',
      thread_id: failureThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  expect(screen.queryByText('AI 제목')).not.toBeInTheDocument();
});

test('reasoning chunks stream into the Inner Monologue panel', async () => {
  // Consolidates `renders live reasoning chunks` + `streams reasoning summary
  // content` — both exercise the same `reasoning` event → Inner Monologue path.
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse(summary({ thread_id: generatedThreadId || 'thread-reasoning', title: 'reasoning 테스트', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await user.type(await screen.findByPlaceholderText(/message orchagent/i), 'reasoning 테스트');
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
      event_type: 'reasoning',
      node: 'head_supervisor',
      display_name: 'Head Supervisor',
      content: '이 turn은 research보다 synthesis가 먼저 필요하다.',
      timestamp: '2026-03-22T10:20:01Z',
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

test('tool_start renders the fallback Inner Monologue summary when no reasoning chunk is streamed', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse(summary({ thread_id: generatedThreadId || 'thread-fallback', title: '작업 파일 생성', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await user.type(
    await screen.findByPlaceholderText(/message orchagent/i),
    'Create a file named hi.txt in the workspace and write hi into it.',
  );
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

  expect(
    await screen.findByText(/Filesystem Write 도구 결과를 바탕으로 응답 근거를 정리하는 중입니다/i),
  ).toBeInTheDocument();
});

test('completed answer triggers suggested-queries fetch and clicking a suggestion injects the composer', async () => {
  const user = userEvent.setup();
  const deferred = deferredSseResponse();
  let generatedThreadId = '';

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) return jsonResponse({ threads: [] });

    if (url.endsWith('/api/chat')) {
      const body = JSON.parse(String(init?.body || '{}'));
      generatedThreadId = body.thread_id;
      return deferred.response;
    }

    if (url.endsWith('/ai-title')) {
      return jsonResponse(summary({ thread_id: generatedThreadId, title: 'RoPE', latest_status: 'running', checkpoint_id: null, message_count: 1 }));
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

  stubCsrfCookie();
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
    { event_type: 'text', node: 'assistant', content: '최종 응답', timestamp: '2026-03-22T10:20:01Z' },
    { event_type: 'checkpoint', thread_id: generatedThreadId, checkpoint_id: 'cp-1', timestamp: '2026-03-22T10:20:02Z' },
    {
      event_type: 'status',
      status: 'completed',
      thread_id: generatedThreadId,
      node: 'assistant',
      display_name: 'Completed',
      timestamp: '2026-03-22T10:20:03Z',
    },
  ]);

  const suggestionButton = await screen.findByRole('button', { name: 'RoPE와 ALiBi 차이도 비교해줘' });
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/suggested-queries'))).toBe(true);

  await user.click(suggestionButton);
  expect(screen.getByDisplayValue('RoPE와 ALiBi 차이도 비교해줘')).toBeInTheDocument();
});

test('marks a thread errored when /api/chat fails and resume failure preserves the interrupt banner', async () => {
  // Consolidates `marks errored on send fail` + `restores interrupted resume
  // state when resume fails` into one test that covers both error pathways
  // in a single render via two sequential scenarios.

  // Scenario 1: send failure.
  const userOne = userEvent.setup();
  const sendFailFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [summary({ thread_id: 'thread-1', title: 'Primary thread', preview: 'Existing answer' })],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: summary({ thread_id: 'thread-1', title: 'Primary thread', preview: 'Existing answer' }),
        messages: [
          { id: 'm-1', role: 'user', content: 'Original question', created_at: '2026-03-22T10:00:00Z' },
          { id: 'm-2', role: 'assistant', content: 'Existing answer', created_at: '2026-03-22T10:01:00Z' },
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

  vi.stubGlobal('fetch', sendFailFetch);
  const { unmount } = renderWorkspace();

  await userOne.click(await screen.findByRole('button', { name: /open thread primary thread/i }));
  await userOne.type(screen.getByPlaceholderText(/message orchagent/i), 'Failing follow up');
  await userOne.click(screen.getByRole('button', { name: /send message/i }));

  await waitFor(() => {
    expect(screen.getByText('Backend exploded')).toBeInTheDocument();
  });
  expect(replaceMock).not.toHaveBeenCalledWith(expect.stringMatching(/^\/c\//));
  expect(screen.getAllByText('Errored').length).toBeGreaterThan(0);

  unmount();

  // Scenario 2: resume failure on an interrupted thread.
  const userTwo = userEvent.setup();
  const resumeFailFetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [summary({ thread_id: 'thread-1', title: 'Interrupted thread', preview: 'Awaiting approval', latest_status: 'interrupted' })],
      });
    }

    if (url.includes('/api/threads/thread-1')) {
      return jsonResponse({
        thread: summary({ thread_id: 'thread-1', title: 'Interrupted thread', preview: 'Awaiting approval', latest_status: 'interrupted' }),
        messages: [
          { id: 'm-1', role: 'user', content: 'Do the risky thing', created_at: '2026-03-22T10:00:00Z' },
          { id: 'm-2', role: 'assistant', content: 'Awaiting approval', created_at: '2026-03-22T10:01:00Z' },
        ],
      });
    }

    if (url.endsWith('/api/chat/resume')) {
      return jsonResponse({ detail: 'Resume failed' }, 500);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', resumeFailFetch);
  renderWorkspace();

  await userTwo.click(await screen.findByRole('button', { name: /open thread interrupted thread/i }));
  expect(await screen.findByText(/action required/i)).toBeInTheDocument();

  await userTwo.click(screen.getByRole('button', { name: /approve & continue/i }));

  await waitFor(() => {
    expect(screen.getByText('Resume failed')).toBeInTheDocument();
  });
  // V-001: interrupt banner remains visible even after resume error.
  expect(screen.getByText(/action required/i)).toBeInTheDocument();
  expect(screen.queryByText(/\[User Action\]: approve/i)).not.toBeInTheDocument();
});

test('toggles a thread pin state and reorders pinned threads to the top', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [
          summary({ thread_id: 'thread-2', title: 'Already top', last_activity_at: '2026-03-22T11:15:00Z', checkpoint_id: 'cp-2' }),
          summary({ thread_id: 'thread-1', title: 'Pin me' }),
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1')) {
      const body = JSON.parse(String(init?.body || '{}'));
      return jsonResponse(summary({ thread_id: 'thread-1', title: 'Pin me', pinned: body.pinned ?? false }));
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  expect(
    (await screen.findAllByRole('button', { name: /open thread/i })).map((b) => b.getAttribute('aria-label'))
  ).toEqual(['Open thread Already top', 'Open thread Pin me']);

  const pinThreadButton = await screen.findByRole('button', { name: /open thread pin me/i });
  await user.hover(pinThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions pin me/i }));
  await user.click(screen.getByRole('button', { name: /pin pin me/i }));

  expect(await screen.findByText('Pinned')).toBeInTheDocument();
  expect(
    screen.getAllByRole('button', { name: /open thread/i }).map((b) => b.getAttribute('aria-label'))
  ).toEqual(['Open thread Pin me', 'Open thread Already top']);
});

test('deletes the active thread and returns to draft', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const telemetryResponse = maybeHandleTelemetryRequest(url);
    if (telemetryResponse) return telemetryResponse;

    if (url.includes('/api/auth/me')) return jsonResponse(authMePayload());
    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({
        threads: [summary({ thread_id: 'thread-1', title: 'Delete me', preview: 'Saved assistant answer' })],
      });
    }

    if (url.includes('/api/threads/thread-1') && (!init || init.method === 'GET')) {
      return jsonResponse({
        thread: summary({ thread_id: 'thread-1', title: 'Delete me', preview: 'Saved assistant answer' }),
        messages: [
          { id: 'm-1', role: 'user', content: 'Delete this thread', created_at: '2026-03-22T10:00:00Z' },
        ],
      });
    }

    if (url.endsWith('/api/threads/thread-1') && init?.method === 'DELETE') {
      return new Response(null, { status: 204 });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  stubCsrfCookie();
  vi.stubGlobal('fetch', fetchMock);
  renderWorkspace();

  await user.click(await screen.findByRole('button', { name: /open thread delete me/i }));
  expect(await screen.findByText('Delete this thread')).toBeInTheDocument();

  const deleteThreadButton = screen.getByRole('button', { name: /open thread delete me/i });
  await user.hover(deleteThreadButton);
  await user.click(screen.getByRole('button', { name: /thread actions delete me/i }));
  await user.click(screen.getByRole('button', { name: /delete delete me/i }));

  expect(replaceMock).toHaveBeenCalledWith('/');
  expect(await screen.findByText('System Ready')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /open thread delete me/i })).not.toBeInTheDocument();
});
