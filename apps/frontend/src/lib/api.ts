import type { AuthUser } from '@/types/auth';
import type { ThreadDetail, ThreadSummary } from '@/types/thread';

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002').replace(/\/$/, '');
const CSRF_COOKIE_NAME = 'orch_csrf';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

export class UnauthorizedError extends Error {
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

function notifyUnauthorized() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }
}

function readCsrfToken(): string {
  if (typeof document === 'undefined') {
    return '';
  }

  const csrfCookie = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${CSRF_COOKIE_NAME}=`));
  if (!csrfCookie) {
    return '';
  }

  return decodeURIComponent(csrfCookie.slice(CSRF_COOKIE_NAME.length + 1));
}

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

async function requestJson<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    headers?: Record<string, string>;
    includeCsrf?: boolean;
  } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers || {}),
  };
  const method = options.method || 'GET';

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.includeCsrf) {
    const csrfToken = readCsrfToken();
    if (csrfToken) {
      headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    credentials: 'include',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 401) {
    notifyUnauthorized();
    throw new UnauthorizedError(await readErrorMessage(response));
  }
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

async function requestStream(
  path: string,
  payload: Record<string, unknown>
): Promise<ReadableStream<Uint8Array>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const csrfToken = readCsrfToken();
  if (csrfToken) {
    headers[CSRF_HEADER_NAME] = csrfToken;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify(payload),
  });

  if (response.status === 401) {
    notifyUnauthorized();
    throw new UnauthorizedError(await readErrorMessage(response));
  }
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

export async function patchThread(params: {
  threadId: string;
  title?: string;
  pinned?: boolean;
  archived?: boolean;
}): Promise<ThreadSummary> {
  return requestJson<ThreadSummary>(`/api/threads/${encodeURIComponent(params.threadId)}`, {
    method: 'PATCH',
    includeCsrf: true,
    body: {
      title: params.title,
      pinned: params.pinned,
      archived: params.archived,
    },
  });
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/me');
}

export async function signupUser(params: {
  loginId: string;
  password: string;
  displayName?: string;
}): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/signup', {
    method: 'POST',
    body: {
      login_id: params.loginId,
      password: params.password,
      display_name: params.displayName || undefined,
    },
  });
}

export async function loginUser(params: {
  loginId: string;
  password: string;
}): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/login', {
    method: 'POST',
    body: {
      login_id: params.loginId,
      password: params.password,
    },
  });
}

export async function logoutUser(): Promise<void> {
  await requestJson<{ message: string }>('/api/auth/logout', {
    method: 'POST',
    includeCsrf: true,
  });
}

export async function changePasswordUser(params: {
  currentPassword: string;
  newPassword: string;
}): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/change-password', {
    method: 'POST',
    includeCsrf: true,
    body: {
      current_password: params.currentPassword,
      new_password: params.newPassword,
    },
  });
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
