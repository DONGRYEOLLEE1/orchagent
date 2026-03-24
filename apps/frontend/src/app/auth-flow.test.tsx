/* eslint-disable @next/next/no-img-element */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import LoginPage from '@/app/(auth)/login/page';
import SignupPage from '@/app/(auth)/signup/page';
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

function renderWithAuth(node: React.ReactNode) {
  return render(<AuthProvider>{node}</AuthProvider>);
}

test('signup form validates confirmation and shows helper text', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/auth/me')) {
      return jsonResponse({ detail: 'Authentication required' }, 401);
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<SignupPage />);

  expect(await screen.findByText(/Password must be at least 4 characters/i)).toBeInTheDocument();
  await user.type(screen.getByLabelText(/login id/i), 'user1');
  await user.type(screen.getByLabelText(/^password$/i), 'abcdefghijklmn1');
  await user.type(screen.getByLabelText(/confirm password/i), 'mismatch');
  await user.click(screen.getByRole('button', { name: /create account/i }));

  expect(await screen.findByText(/Password confirmation does not match/i)).toBeInTheDocument();
});

test('login redirects to the workspace after success', async () => {
  const user = userEvent.setup();
  let meCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      meCalls += 1;
      if (meCalls === 1) {
        return jsonResponse({ detail: 'Authentication required' }, 401);
      }
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.endsWith('/api/auth/login')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<LoginPage />);

  await user.type(screen.getByLabelText(/login id/i), 'user1');
  await user.type(screen.getByLabelText(/password/i), 'abcdefghijklmn1');
  await user.click(screen.getByRole('button', { name: /log in/i }));

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith('/');
  });
});

test('workspace auth guard redirects unauthenticated users to login', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/auth/me')) {
      return jsonResponse({ detail: 'Authentication required' }, 401);
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});

test('workspace logout clears auth and redirects to login', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
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

    if (url.endsWith('/api/auth/logout')) {
      expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-token');
      return jsonResponse({ message: 'Logged out' });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  await user.click(await screen.findByRole('button', { name: /log out/i }));

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});

test('must-change-password flow unlocks the workspace after success', async () => {
  const user = userEvent.setup();
  let meCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      meCalls += 1;
      return jsonResponse({
        id: 'admin-1',
        login_id: 'admin',
        role: 'admin',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: meCalls === 1,
      });
    }

    if (url.endsWith('/api/auth/change-password')) {
      expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('csrf-token');
      return jsonResponse({
        id: 'admin-1',
        login_id: 'admin',
        role: 'admin',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  await user.type(await screen.findByLabelText(/current password/i), 'admin1');
  await user.type(screen.getByLabelText(/new password/i), 'abcdefghijklmn2');
  await user.click(screen.getByRole('button', { name: /change password/i }));

  expect(await screen.findByText(/System Ready/i)).toBeInTheDocument();
});

test('workspace redirects to login when a protected fetch returns 401', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
        role: 'user',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ detail: 'Authentication required' }, 401);
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});

test('profile panel saves and updates the visible user state', async () => {
  const user = userEvent.setup();
  let meCalls = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      meCalls += 1;
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
        role: 'user',
        status: 'active',
        display_name: meCalls === 1 ? null : 'Updated Name',
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/users/me')) {
      expect(init?.method).toBe('PATCH');
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
        role: 'user',
        status: 'active',
        display_name: 'Updated Name',
        email: 'updated@example.com',
        must_change_password: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  await user.type(await screen.findByLabelText(/display name/i), 'Updated Name');
  await user.type(screen.getByLabelText(/email/i), 'updated@example.com');
  await user.click(screen.getByRole('button', { name: /save profile/i }));

  expect(await screen.findByDisplayValue('Updated Name')).toBeInTheDocument();
  expect(screen.getByText('Updated Name')).toBeInTheDocument();
});

test('admin status panel is only rendered for admins and can submit a status change', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'admin-1',
        login_id: 'admin',
        role: 'admin',
        status: 'active',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/threads?limit=50')) {
      return jsonResponse({ threads: [] });
    }

    if (url.endsWith('/api/users/user-2')) {
      expect(init?.method).toBe('PATCH');
      return jsonResponse({
        id: 'user-2',
        login_id: 'user2',
        role: 'user',
        status: 'disabled',
        display_name: null,
        email: null,
        must_change_password: false,
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  Object.defineProperty(document, 'cookie', {
    configurable: true,
    get: () => 'orch_csrf=csrf-token',
  });
  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  expect(await screen.findByText(/Admin User Status/i)).toBeInTheDocument();
  await user.type(screen.getByLabelText(/target user id/i), 'user-2');
  await user.selectOptions(screen.getByLabelText(/status/i), 'disabled');
  await user.click(screen.getByRole('button', { name: /update status/i }));

  expect(await screen.findByText(/Updated user2 to disabled/i)).toBeInTheDocument();
});

test('admin status panel is hidden for non-admin users', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'user1',
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

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderWithAuth(<ChatWorkspace />);

  expect(await screen.findByText(/System Ready/i)).toBeInTheDocument();
  expect(screen.queryByText(/Admin User Status/i)).not.toBeInTheDocument();
});
