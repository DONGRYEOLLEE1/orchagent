import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

import { AuthProvider } from '@/components/auth/AuthProvider';
import DashboardPage from '@/app/dashboard/page';

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

function renderDashboard() {
  return render(
    <AuthProvider>
      <DashboardPage />
    </AuthProvider>
  );
}

test('renders dashboard metrics, chart heading, and live trace table', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: 'Tester',
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/dashboard/summary')) {
      return jsonResponse({
        user_id: 'user-1',
        total_turns: 12,
        completed_turns: 11,
        total_input_tokens: 1200,
        total_output_tokens: 3400,
        total_tokens: 4600,
        total_reasoning_tokens: 900,
        total_cost_microusd: 4120500000,
        exact_total_cost_microusd: 4120500000,
        estimated_total_cost_microusd: 0,
        exact_reasoning_cost_microusd: 0,
        estimated_reasoning_cost_microusd: 500000000,
        avg_latency_ms: 248,
        avg_ttft_ms: 91,
        total_tool_calls: 18,
      });
    }

    if (url.includes('/api/dashboard/daily-usage')) {
      return jsonResponse({
        user_id: 'user-1',
        points: [
          { usage_date: '2026-03-21', input_tokens: 100, output_tokens: 180, total_tokens: 280, reasoning_tokens: 60, total_cost_microusd: 1000000 },
          { usage_date: '2026-03-22', input_tokens: 180, output_tokens: 260, total_tokens: 440, reasoning_tokens: 90, total_cost_microusd: 1400000 },
          { usage_date: '2026-03-23', input_tokens: 220, output_tokens: 340, total_tokens: 560, reasoning_tokens: 140, total_cost_microusd: 1900000 },
        ],
      });
    }

    if (url.includes('/api/dashboard/live-traces')) {
      return jsonResponse({
        user_id: 'user-1',
        rows: [
          {
            timestamp: '2026-03-24T09:00:00Z',
            user_id: 'user-1',
            thread_id: 'thread-1',
            turn_id: 'turn-1',
            turn_index: 1,
            request_kind: 'chat',
            model: 'gpt-5.4-mini',
            input_tokens: 32,
            output_tokens: 88,
            reasoning_tokens: 20,
            latency_ms: 248,
            ttft_ms: 91,
            status: 'completed',
            active_team_final: 'research',
          },
        ],
      });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderDashboard();

  expect(await screen.findByText('OrchAgent Monitor')).toBeInTheDocument();
  expect(screen.getByText('Daily Total Token Consumption')).toBeInTheDocument();
  expect(screen.getByText('Quota Utilization')).toBeInTheDocument();
  expect(screen.getByText('Real-time Service Trace')).toBeInTheDocument();
  expect(screen.getByText('$4,120.50')).toBeInTheDocument();
  expect(screen.getByText('gpt-5.4-mini')).toBeInTheDocument();
});

test('dashboard top navigation routes between chat and dashboard', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.includes('/api/auth/me')) {
      return jsonResponse({
        id: 'user-1',
        login_id: 'tester',
        role: 'user',
        status: 'active',
        display_name: 'Tester',
        email: null,
        must_change_password: false,
      });
    }

    if (url.includes('/api/dashboard/summary')) {
      return jsonResponse({
        user_id: 'user-1',
        total_turns: 1,
        completed_turns: 1,
        total_input_tokens: 10,
        total_output_tokens: 20,
        total_tokens: 30,
        total_reasoning_tokens: 0,
        total_cost_microusd: 0,
        exact_total_cost_microusd: 0,
        estimated_total_cost_microusd: 0,
        exact_reasoning_cost_microusd: 0,
        estimated_reasoning_cost_microusd: 0,
        avg_latency_ms: 10,
        avg_ttft_ms: 5,
        total_tool_calls: 0,
      });
    }

    if (url.includes('/api/dashboard/daily-usage')) {
      return jsonResponse({ user_id: 'user-1', points: [] });
    }

    if (url.includes('/api/dashboard/live-traces')) {
      return jsonResponse({ user_id: 'user-1', rows: [] });
    }

    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderDashboard();

  await user.click(await screen.findByRole('button', { name: 'Chat' }));

  expect(pushMock).toHaveBeenCalledWith('/');
});

test('redirects unauthenticated users to login', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/auth/me')) {
      return jsonResponse({ detail: 'Authentication required' }, 401);
    }
    throw new Error(`Unhandled fetch: ${url}`);
  });

  vi.stubGlobal('fetch', fetchMock);

  renderDashboard();

  await waitFor(() => {
    expect(replaceMock).toHaveBeenCalledWith('/login');
  });
});
