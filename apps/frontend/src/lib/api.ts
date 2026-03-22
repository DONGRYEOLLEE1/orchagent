import type { ThreadDetail, ThreadSummary } from '@/types/thread';

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002').replace(/\/$/, '');

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === 'string') {
      return payload.detail;
    }
  } catch {
    // Ignore non-JSON error bodies and fall back to the status message below.
  }

  return `Request failed with status ${response.status}`;
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

async function requestStream(
  path: string,
  payload: Record<string, unknown>
): Promise<ReadableStream<Uint8Array>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  if (!response.body) {
    throw new Error('No response body received.');
  }

  return response.body;
}

export async function fetchThreads(limit = 50): Promise<ThreadSummary[]> {
  const payload = await requestJson<{ threads: ThreadSummary[] }>(`/api/threads?limit=${limit}`);
  return payload.threads;
}

export async function fetchThreadDetail(threadId: string): Promise<ThreadDetail> {
  return requestJson<ThreadDetail>(`/api/threads/${encodeURIComponent(threadId)}`);
}

export async function sendChatStream(params: {
  message: string;
  threadId: string;
  images?: string[];
}): Promise<ReadableStream<Uint8Array>> {
  return requestStream('/api/chat', {
    message: params.message,
    thread_id: params.threadId,
    images: params.images && params.images.length > 0 ? params.images : undefined,
  });
}

export async function resumeChatStream(params: {
  threadId: string;
  action: string;
  feedback?: string;
}): Promise<ReadableStream<Uint8Array>> {
  return requestStream('/api/chat/resume', {
    thread_id: params.threadId,
    action: params.action,
    feedback: params.feedback || undefined,
  });
}
