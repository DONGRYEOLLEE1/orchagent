import { render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import SettingsProfilePage from '@/app/settings/profile/page';

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

test('renders profile settings and dedicated change password section', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

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

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <SettingsProfilePage />
    </AuthProvider>
  );

  expect(await screen.findByText('Profile & Password')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Change Password', level: 2 })).toBeInTheDocument();
  expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
});
