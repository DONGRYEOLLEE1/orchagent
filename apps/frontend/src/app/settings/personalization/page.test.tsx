import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import SettingsPersonalizationPage from '@/app/settings/personalization/page';

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

test('renders personalization editor and saves grouped instruction fields', async () => {
  const user = userEvent.setup();
  let instructions = [
    {
      id: 'instruction-1',
      user_id: 'user-1',
      instruction_type: 'user_profile',
      title: 'About You',
      content_text: 'Senior software architect',
      enabled: true,
      created_at: '2026-03-26T09:00:00+09:00',
      updated_at: '2026-03-26T09:00:00+09:00',
    },
    {
      id: 'instruction-2',
      user_id: 'user-1',
      instruction_type: 'response_style',
      title: 'Response Style',
      content_text: 'Be concise and direct.',
      enabled: true,
      created_at: '2026-03-26T09:00:00+09:00',
      updated_at: '2026-03-26T09:00:00+09:00',
    },
  ];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || 'GET').toUpperCase();
    const body =
      typeof init?.body === 'string' && init.body.length > 0
        ? JSON.parse(init.body)
        : null;

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

    if (url.includes('/api/users/me/personalization/settings') && method === 'GET') {
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

    if (url.includes('/api/users/me/personalization/settings') && method === 'PATCH') {
      return jsonResponse({
        user_id: 'user-1',
        memory_enabled: true,
        instructions_enabled: true,
        allow_explicit_memory: true,
        allow_inferred_memory: true,
        allow_chat_history_reference: true,
        default_memory_mode: 'enabled',
        created_at: '2026-03-26T09:00:00+09:00',
        updated_at: '2026-03-30T09:00:00+09:00',
      });
    }

    if (url.includes('/api/users/me/personalization/instructions') && method === 'GET') {
      return jsonResponse({ instructions });
    }

    if (url.includes('/api/users/me/personalization/instructions/') && method === 'PATCH') {
      const instructionId = url.split('/').pop() || '';
      instructions = instructions.map((instruction) =>
        instruction.id === instructionId
          ? {
              ...instruction,
              title: body.title ?? instruction.title,
              content_text: body.content_text ?? instruction.content_text,
              instruction_type: body.instruction_type ?? instruction.instruction_type,
              enabled: body.enabled ?? instruction.enabled,
            }
          : instruction
      );
      return jsonResponse(instructions.find((instruction) => instruction.id === instructionId));
    }

    if (url.endsWith('/api/users/me/personalization/instructions') && method === 'POST') {
      const created = {
        id: `instruction-${instructions.length + 1}`,
        user_id: 'user-1',
        instruction_type: body.instruction_type,
        title: body.title,
        content_text: body.content_text,
        enabled: body.enabled ?? true,
        created_at: '2026-03-30T09:00:00+09:00',
        updated_at: '2026-03-30T09:00:00+09:00',
      };
      instructions = [...instructions, created];
      return jsonResponse(created, 201);
    }

    if (url.includes('/api/users/me/personalization/instructions/') && method === 'DELETE') {
      const instructionId = url.split('/').pop() || '';
      instructions = instructions.filter((instruction) => instruction.id !== instructionId);
      return noContentResponse();
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <SettingsPersonalizationPage />
    </AuthProvider>
  );

  expect(await screen.findByRole('heading', { name: 'Personalization', level: 1 })).toBeInTheDocument();
  const aboutYouField = await screen.findByLabelText('About You');
  const responseStyleField = await screen.findByLabelText('Response Style');
  expect(aboutYouField).toHaveValue('Senior software architect');
  expect(responseStyleField).toHaveValue('Be concise and direct.');

  await user.clear(aboutYouField);
  await user.type(aboutYouField, 'Senior software architect focused on AI agents');
  await user.clear(responseStyleField);
  await user.type(responseStyleField, 'Use bullet points and stay concise.');
  await user.click(screen.getByRole('button', { name: 'Save Personalization' }));

  await waitFor(() => {
    expect(screen.getByText('Personalization settings saved.')).toBeInTheDocument();
  });

  expect(screen.getByLabelText('About You')).toHaveValue('Senior software architect focused on AI agents');
  expect(screen.getByLabelText('Response Style')).toHaveValue('Use bullet points and stay concise.');
});
