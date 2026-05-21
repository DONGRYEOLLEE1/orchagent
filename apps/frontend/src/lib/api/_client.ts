// Phase 3.4 — common HTTP plumbing for the OrchAgent API client.
// Shared between every domain module (threads / chat / auth / memory / uploads /
// repositories / dashboard) so CSRF handling, base URL, and 401 redirects live
// in exactly one place. The legacy ``lib/api.ts`` re-exports from here while
// per-domain modules migrate over.

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002').replace(
  /\/$/,
  '',
);
export const CSRF_COOKIE_NAME = 'orch_csrf';
export const CSRF_HEADER_NAME = 'X-CSRF-Token';

export class UnauthorizedError extends Error {
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

export function notifyUnauthorized(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }
}

export function readCsrfToken(): string {
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

export async function readErrorMessage(response: Response): Promise<string> {
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

export interface RequestJsonOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  includeCsrf?: boolean;
}

export async function requestJson<T>(
  path: string,
  options: RequestJsonOptions = {},
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
