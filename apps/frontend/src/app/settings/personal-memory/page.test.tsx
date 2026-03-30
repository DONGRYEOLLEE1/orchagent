import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import SettingsPersonalMemoryPage from '@/app/settings/personal-memory/page';

const replaceMock = vi.fn();
const pushMock = vi.fn();

beforeEach(() => {
  replaceMock.mockReset();
  pushMock.mockReset();
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: pushMock,
  }),
}));

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function noContentResponse(status = 204): Response {
  return new Response(null, { status });
}

test('shows memory action menu and KST saved-at helper copy', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: 'Tester',
        email: 'tester@example.com',
        must_change_password: false,
      });
    }

    if (url.includes('/api/users/me/memory/settings')) {
      return jsonResponse({
        user_id: 'user-1',
        memory_enabled: true,
        instructions_enabled: true,
        allow_explicit_memory: true,
        allow_inferred_memory: true,
        allow_chat_history_reference: true,
        default_memory_mode: 'enabled',
        created_at: '2026-03-26T09:00:00+09:00',
        updated_at: '2026-03-26T09:00:00+09:00',
      });
    }

    if (url.includes('/api/users/me/memory?limit=100')) {
      return jsonResponse({
        memories: [
          {
            id: 'memory-1',
            user_id: 'user-1',
            thread_id: null,
            scope_type: 'user_global',
            source_type: 'inferred',
            status: 'active',
            category: 'personal_interest',
            title: '좋아하는 아티스트',
            content_text: '가수 백예린을 좋아한다',
            confidence: 91,
            salience: 88,
            created_at: '2026-03-26T09:00:00+09:00',
            updated_at: '2026-03-26T09:00:00+09:00',
            deleted_at: null,
          },
        ],
      });
    }

    if (url.includes('/api/users/me/memory/') && method === 'DELETE') {
      return noContentResponse();
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <SettingsPersonalMemoryPage />
    </AuthProvider>
  );

  expect(await screen.findByRole('heading', { name: 'Personal Memory', level: 1 })).toBeInTheDocument();
  expect(await screen.findByText('가수 백예린을 좋아한다')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /memory actions 좋아하는 아티스트/i }));

  expect(screen.getByText('삭제')).toBeInTheDocument();
  expect(screen.getByText('2026년 03월 26일에 저장되었음')).toBeInTheDocument();
});
