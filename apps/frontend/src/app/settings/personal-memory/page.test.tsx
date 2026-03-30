import { render, screen, waitFor } from '@testing-library/react';
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

function buildFetchMock() {
  let instructionsEnabled = true;
  let instructions = [
    {
      id: 'instruction-1',
      user_id: 'user-1',
      instruction_type: 'response_style',
      title: '답변 언어',
      content_text: '한국어 답변을 선호한다',
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

    if (url.includes('/api/users/me/memory/settings')) {
      return jsonResponse({
        user_id: 'user-1',
        memory_enabled: true,
        instructions_enabled: instructionsEnabled,
        allow_explicit_memory: true,
        allow_inferred_memory: true,
        allow_chat_history_reference: true,
        default_memory_mode: 'enabled',
        created_at: '2026-03-26T09:00:00+09:00',
        updated_at: '2026-03-26T09:00:00+09:00',
      });
    }

    if (url.includes('/api/users/me/personalization/settings') && method === 'GET') {
      return jsonResponse({
        user_id: 'user-1',
        memory_enabled: true,
        instructions_enabled: instructionsEnabled,
        allow_explicit_memory: true,
        allow_inferred_memory: true,
        allow_chat_history_reference: true,
        default_memory_mode: 'enabled',
        created_at: '2026-03-26T09:00:00+09:00',
        updated_at: '2026-03-26T09:00:00+09:00',
      });
    }

    if (url.includes('/api/users/me/personalization/settings') && method === 'PATCH') {
      instructionsEnabled = Boolean(body?.instructions_enabled);
      return jsonResponse({
        user_id: 'user-1',
        memory_enabled: true,
        instructions_enabled: instructionsEnabled,
        allow_explicit_memory: true,
        allow_inferred_memory: true,
        allow_chat_history_reference: true,
        default_memory_mode: 'enabled',
        created_at: '2026-03-26T09:00:00+09:00',
        updated_at: '2026-03-27T09:00:00+09:00',
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

    if (url.includes('/api/users/me/personalization/instructions') && method === 'GET') {
      return jsonResponse({ instructions });
    }

    if (url.endsWith('/api/users/me/personalization/instructions') && method === 'POST') {
      const created = {
        id: `instruction-${instructions.length + 1}`,
        user_id: 'user-1',
        instruction_type: body.instruction_type,
        title: body.title,
        content_text: body.content_text,
        enabled: body.enabled ?? true,
        created_at: '2026-03-28T09:00:00+09:00',
        updated_at: '2026-03-28T09:00:00+09:00',
      };
      instructions = [created, ...instructions];
      return jsonResponse(created, 201);
    }

    if (url.includes('/api/users/me/personalization/instructions/') && method === 'PATCH') {
      const instructionId = url.split('/').pop() || '';
      instructions = instructions.map((instruction) =>
        instruction.id === instructionId
          ? {
              ...instruction,
              instruction_type: body.instruction_type ?? instruction.instruction_type,
              title: body.title ?? instruction.title,
              content_text: body.content_text ?? instruction.content_text,
              enabled: body.enabled ?? instruction.enabled,
              updated_at: '2026-03-29T09:00:00+09:00',
            }
          : instruction
      );
      const updated = instructions.find((instruction) => instruction.id === instructionId);
      return jsonResponse(updated);
    }

    if (url.includes('/api/users/me/personalization/instructions/') && method === 'DELETE') {
      const instructionId = url.split('/').pop() || '';
      instructions = instructions.filter((instruction) => instruction.id !== instructionId);
      return noContentResponse();
    }

    if (url.includes('/api/users/me/memory/') && method === 'DELETE') {
      return noContentResponse();
    }

    throw new Error(`Unhandled fetch: ${method} ${url}`);
  });

  return fetchMock;
}

test('shows memory action menu and KST saved-at helper copy', async () => {
  const user = userEvent.setup();
  const fetchMock = buildFetchMock();

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

test('manages personalization instructions inline', async () => {
  const user = userEvent.setup();
  const fetchMock = buildFetchMock();

  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <SettingsPersonalMemoryPage />
    </AuthProvider>
  );

  expect(await screen.findByText('한국어 답변을 선호한다')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Enable instructions policy' })).toHaveAttribute('aria-pressed', 'true');

  await user.click(screen.getByRole('button', { name: '새 지침 추가' }));
  await user.selectOptions(screen.getByLabelText('Instruction type'), 'user_profile');
  await user.type(screen.getByLabelText('Instruction title'), '직업');
  await user.type(screen.getByLabelText('Instruction content'), 'AI Engineer');
  await user.click(screen.getByRole('button', { name: 'Create Instruction' }));

  expect(await screen.findByText('직업')).toBeInTheDocument();
  expect(screen.getByText('AI Engineer')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /Disable instruction 직업/i }));
  expect(await screen.findByRole('button', { name: /Enable instruction 직업/i })).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /Instruction actions 직업/i }));
  await user.click(screen.getByRole('button', { name: '편집' }));

  const contentField = screen.getByLabelText('Instruction content');
  await user.clear(contentField);
  await user.type(contentField, 'AI Agent Engineer');
  await user.click(screen.getByRole('button', { name: 'Save Changes' }));

  expect(await screen.findByText('AI Agent Engineer')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Enable instructions policy' }));
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Enable instructions policy' })).toHaveAttribute('aria-pressed', 'false');
  });

  await user.click(screen.getByRole('button', { name: /Instruction actions 직업/i }));
  await user.click(screen.getByRole('button', { name: '삭제' }));

  await waitFor(() => {
    expect(screen.queryByText('AI Agent Engineer')).not.toBeInTheDocument();
  });
});
