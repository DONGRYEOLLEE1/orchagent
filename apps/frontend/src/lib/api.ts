import type { AuthUser } from '@/types/auth';
import type {
  DashboardDailyUsageResponse,
  DashboardLiveTracesResponse,
  DashboardSummary,
} from '@/types/dashboard';
import type {
  PersonalMemoryEntry,
  PersonalizationInstruction,
  PersonalizationInstructionType,
  UserMemorySettings,
} from '@/types/memory';
import type { ThreadDetail, ThreadSummary, ThreadTelemetry } from '@/types/thread';

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

export async function fetchThreadTelemetry(threadId: string): Promise<ThreadTelemetry> {
  return requestJson<ThreadTelemetry>(`/api/threads/${encodeURIComponent(threadId)}/telemetry`);
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

export async function generateAiThreadTitle(params: {
  threadId: string;
  message?: string;
}): Promise<ThreadSummary> {
  return requestJson<ThreadSummary>(`/api/threads/${encodeURIComponent(params.threadId)}/ai-title`, {
    method: 'POST',
    includeCsrf: true,
    body: params.message !== undefined ? { message: params.message } : {},
  });
}

export async function generateSuggestedQueries(params: {
  threadId: string;
}): Promise<ThreadTelemetry> {
  return requestJson<ThreadTelemetry>(
    `/api/threads/${encodeURIComponent(params.threadId)}/suggested-queries`,
    {
      method: 'POST',
      includeCsrf: true,
    }
  );
}

async function requestNoContent(
  path: string,
  options: {
    method: string;
    includeCsrf?: boolean;
  }
): Promise<void> {
  const headers: Record<string, string> = {};
  if (options.includeCsrf) {
    const csrfToken = readCsrfToken();
    if (csrfToken) {
      headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    credentials: 'include',
    headers,
  });
  if (response.status === 401) {
    notifyUnauthorized();
    throw new UnauthorizedError(await readErrorMessage(response));
  }
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
}

export async function deleteThread(threadId: string): Promise<void> {
  await requestNoContent(`/api/threads/${encodeURIComponent(threadId)}`, {
    method: 'DELETE',
    includeCsrf: true,
  });
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/me');
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return requestJson<DashboardSummary>('/api/dashboard/summary');
}

export async function fetchDashboardDailyUsage(): Promise<DashboardDailyUsageResponse> {
  return requestJson<DashboardDailyUsageResponse>('/api/dashboard/daily-usage');
}

export async function fetchDashboardLiveTraces(limit = 20): Promise<DashboardLiveTracesResponse> {
  return requestJson<DashboardLiveTracesResponse>(`/api/dashboard/live-traces?limit=${limit}`);
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

export async function patchCurrentUser(params: {
  displayName?: string;
  email?: string;
}): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/users/me', {
    method: 'PATCH',
    includeCsrf: true,
    body: {
      display_name: params.displayName,
      email: params.email,
    },
  });
}

export async function patchAdminUser(params: {
  userId: string;
  status: string;
}): Promise<AuthUser> {
  return requestJson<AuthUser>(`/api/users/${encodeURIComponent(params.userId)}`, {
    method: 'PATCH',
    includeCsrf: true,
    body: {
      status: params.status,
    },
  });
}

export async function fetchMemorySettings(): Promise<UserMemorySettings> {
  return requestJson<UserMemorySettings>('/api/users/me/memory/settings');
}

export async function fetchPersonalizationSettings(): Promise<UserMemorySettings> {
  return requestJson<UserMemorySettings>('/api/users/me/personalization/settings');
}

export async function patchMemorySettings(params: {
  memoryEnabled?: boolean;
  instructionsEnabled?: boolean;
  allowExplicitMemory?: boolean;
  allowInferredMemory?: boolean;
  allowChatHistoryReference?: boolean;
  defaultMemoryMode?: string;
}): Promise<UserMemorySettings> {
  return requestJson<UserMemorySettings>('/api/users/me/memory/settings', {
    method: 'PATCH',
    includeCsrf: true,
    body: {
      memory_enabled: params.memoryEnabled,
      instructions_enabled: params.instructionsEnabled,
      allow_explicit_memory: params.allowExplicitMemory,
      allow_inferred_memory: params.allowInferredMemory,
      allow_chat_history_reference: params.allowChatHistoryReference,
      default_memory_mode: params.defaultMemoryMode,
    },
  });
}

export async function patchPersonalizationSettings(params: {
  instructionsEnabled?: boolean;
}): Promise<UserMemorySettings> {
  return requestJson<UserMemorySettings>('/api/users/me/personalization/settings', {
    method: 'PATCH',
    includeCsrf: true,
    body: {
      instructions_enabled: params.instructionsEnabled,
    },
  });
}

export async function fetchPersonalMemories(limit = 100): Promise<PersonalMemoryEntry[]> {
  const payload = await requestJson<{ memories: PersonalMemoryEntry[] }>(`/api/users/me/memory?limit=${limit}`);
  return payload.memories;
}

export async function deletePersonalMemory(memoryId: string): Promise<void> {
  await requestNoContent(`/api/users/me/memory/${encodeURIComponent(memoryId)}`, {
    method: 'DELETE',
    includeCsrf: true,
  });
}

export async function fetchPersonalizationInstructions(): Promise<PersonalizationInstruction[]> {
  const payload = await requestJson<{ instructions: PersonalizationInstruction[] }>(
    '/api/users/me/personalization/instructions'
  );
  return payload.instructions;
}

export async function createPersonalizationInstruction(params: {
  instructionType: PersonalizationInstructionType;
  title: string;
  contentText: string;
  enabled?: boolean;
}): Promise<PersonalizationInstruction> {
  return requestJson<PersonalizationInstruction>('/api/users/me/personalization/instructions', {
    method: 'POST',
    includeCsrf: true,
    body: {
      instruction_type: params.instructionType,
      title: params.title,
      content_text: params.contentText,
      enabled: params.enabled ?? true,
    },
  });
}

export async function updatePersonalizationInstruction(params: {
  instructionId: string;
  instructionType?: PersonalizationInstructionType;
  title?: string;
  contentText?: string;
  enabled?: boolean;
}): Promise<PersonalizationInstruction> {
  return requestJson<PersonalizationInstruction>(
    `/api/users/me/personalization/instructions/${encodeURIComponent(params.instructionId)}`,
    {
      method: 'PATCH',
      includeCsrf: true,
      body: {
        instruction_type: params.instructionType,
        title: params.title,
        content_text: params.contentText,
        enabled: params.enabled,
      },
    }
  );
}

export async function deletePersonalizationInstruction(instructionId: string): Promise<void> {
  await requestNoContent(
    `/api/users/me/personalization/instructions/${encodeURIComponent(instructionId)}`,
    {
      method: 'DELETE',
      includeCsrf: true,
    }
  );
}

export async function sendChatStream(params: {
  message: string;
  threadId: string;
  attachmentIds?: string[];
}): Promise<ReadableStream<Uint8Array>> {
  return requestStream('/api/chat', {
    message: params.message,
    thread_id: params.threadId,
    attachment_ids:
      params.attachmentIds && params.attachmentIds.length > 0
        ? params.attachmentIds
        : undefined,
  });
}

export interface UploadedAttachment {
  id: string;
  input_index?: number | null;
  kind: 'image' | 'pdf' | 'spreadsheet' | 'csv' | 'json' | 'docx' | 'artifact';
  source_type?: string;
  processing_status?: string;
  preview_status?: string;
  file_name: string;
  declared_extension?: string | null;
  mime_type: string;
  sniffed_mime_type?: string | null;
  size_bytes: number;
  created_at: string | null;
}

export interface UploadBatchError {
  input_index: number;
  file_name: string;
  error_code: string;
  detail: string;
}

export interface UploadBatchResult {
  uploads: UploadedAttachment[];
  errors: UploadBatchError[];
  accepted_count: number;
  failed_count: number;
  total_size_bytes: number;
}

export async function uploadChatAttachments(params: {
  threadId: string;
  files: File[];
}): Promise<UploadBatchResult> {
  const formData = new FormData();
  formData.set('thread_id', params.threadId);
  for (const file of params.files) {
    formData.append('files', file);
  }

  const headers: Record<string, string> = {};
  const csrfToken = readCsrfToken();
  if (csrfToken) {
    headers[CSRF_HEADER_NAME] = csrfToken;
  }

  const response = await fetch(`${API_BASE_URL}/api/uploads`, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: formData,
  });
  if (response.status === 401) {
    notifyUnauthorized();
    throw new UnauthorizedError(await readErrorMessage(response));
  }
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as UploadBatchResult;
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
