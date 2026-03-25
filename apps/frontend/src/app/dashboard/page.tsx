"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Activity,
  Loader2,
  ShieldCheck,
  Wallet,
} from 'lucide-react';

import { AccountDrawer } from '@/components/workspace/AccountDrawer';
import { WorkspaceTopNav } from '@/components/workspace/WorkspaceTopNav';
import { useAuth } from '@/components/auth/AuthProvider';
import { fetchDashboardDailyUsage, fetchDashboardLiveTraces, fetchDashboardSummary } from '@/lib/api';
import type {
  DashboardDailyUsagePoint,
  DashboardLiveTraceRow,
  DashboardSummary,
} from '@/types/dashboard';
import type { AuthUser } from '@/types/auth';

type LoadState = 'idle' | 'loading' | 'success' | 'error';

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: value >= 1000 ? 1 : 0,
  }).format(value);
}

function formatFullNumber(value: number) {
  return new Intl.NumberFormat('en-US').format(value);
}

function formatCurrencyFromMicrousd(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value / 1_000_000);
}

function formatLatency(value: number | null) {
  if (value == null) return 'N/A';
  return `${value}ms`;
}

function formatTokenBreakdown(summary: DashboardSummary) {
  return `In ${formatCompactNumber(summary.total_input_tokens)} / Out ${formatCompactNumber(summary.total_output_tokens)}`;
}

function formatInferenceCost(summary: DashboardSummary) {
  return formatCurrencyFromMicrousd(summary.total_inference_cost_microusd);
}

function formatUsageDate(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(new Date(value));
}

function buildUsagePath(points: DashboardDailyUsagePoint[], width: number, height: number) {
  if (points.length === 0) return '';
  const maxValue = Math.max(...points.map((point) => point.total_tokens), 1);
  return points
    .map((point, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
      const y = height - (point.total_tokens / maxValue) * height;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

function buildAreaPath(points: DashboardDailyUsagePoint[], width: number, height: number) {
  const linePath = buildUsagePath(points, width, height);
  if (!linePath || points.length === 0) return '';
  return `${linePath} L ${width} ${height} L 0 ${height} Z`;
}

function TokenUsageChart({ points }: { points: DashboardDailyUsagePoint[] }) {
  const width = 620;
  const height = 220;
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const linePath = buildUsagePath(points, width, height);
  const areaPath = buildAreaPath(points, width, height);
  const peakPoint = useMemo(() => {
    if (points.length === 0) return null;
    return points.reduce((highest, point) => (
      point.total_tokens > highest.total_tokens ? point : highest
    ), points[0]);
  }, [points]);
  const hoveredPoint = hoveredIndex != null ? points[hoveredIndex] : null;
  const hoveredX = hoveredIndex != null && points.length > 1
    ? (hoveredIndex / (points.length - 1)) * width
    : width / 2;
  const hoveredY = hoveredPoint
    ? height - (hoveredPoint.total_tokens / Math.max(...points.map((point) => point.total_tokens), 1)) * height
    : null;

  const handlePointerMove = (event: React.MouseEvent<SVGSVGElement>) => {
    if (points.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const ratio = rect.width === 0 ? 0 : Math.max(0, Math.min(x / rect.width, 1));
    const index = points.length === 1 ? 0 : Math.round(ratio * (points.length - 1));
    setHoveredIndex(index);
  };

  return (
    <section className="min-h-[17rem] rounded-[14px] bg-[rgba(31,34,44,0.78)] px-5 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-[var(--font-display)] text-[17px] font-semibold text-white">Daily Total Token Consumption</h2>
          <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-[rgba(170,170,179,0.68)]">
            system-wide processing aggregate
          </p>
        </div>
        <div className="flex items-center gap-2 text-[9px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.76)]">
          <span className="h-2 w-2 rounded-full bg-[#5ef2ff]" />
          Total system usage
        </div>
      </div>

      <div className="mt-5 h-[13.5rem] w-full">
        <svg
          data-testid="token-usage-chart"
          viewBox={`0 0 ${width} ${height}`}
          className="h-full w-full overflow-visible"
          onMouseMove={handlePointerMove}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          {[0.25, 0.5, 0.75].map((ratio) => (
            <line
              key={ratio}
              x1="0"
              x2={width}
              y1={height * ratio}
              y2={height * ratio}
              stroke="rgba(255,255,255,0.08)"
              strokeDasharray="5 8"
            />
          ))}
          {areaPath ? (
            <path d={areaPath} fill="url(#tokenArea)" opacity="0.45" />
          ) : null}
          {linePath ? (
            <path
              d={linePath}
              fill="none"
              stroke="#16efff"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null}
          {hoveredPoint && hoveredY != null ? (
            <>
              <line
                x1={hoveredX}
                x2={hoveredX}
                y1="0"
                y2={height}
                stroke="rgba(94,242,255,0.22)"
                strokeDasharray="4 6"
              />
              <circle
                cx={hoveredX}
                cy={hoveredY}
                r="5"
                fill="#16efff"
                stroke="rgba(8,11,18,0.92)"
                strokeWidth="2"
              />
            </>
          ) : null}
          <defs>
            <linearGradient id="tokenArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(22,239,255,0.34)" />
              <stop offset="100%" stopColor="rgba(22,239,255,0.02)" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      {peakPoint ? (
        <div className="mt-[-2.4rem] flex items-start justify-between gap-4">
          {hoveredPoint ? (
            <div className="rounded-[8px] border border-[rgba(94,242,255,0.18)] bg-[rgba(10,14,22,0.94)] px-3 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[rgba(170,170,179,0.64)]">
                {formatUsageDate(hoveredPoint.usage_date)}
              </div>
              <div className="mt-1 text-[11px] font-semibold text-[#8ff5ff]">
                {formatFullNumber(hoveredPoint.total_tokens)} tokens
              </div>
            </div>
          ) : <div />}
          <div className="rounded-[8px] border border-[rgba(255,255,255,0.06)] bg-[rgba(13,16,24,0.92)] px-3 py-2 text-right">
            <div className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[rgba(170,170,179,0.64)]">
              Peak Day
            </div>
            <div className="mt-1 text-[11px] font-semibold text-[#8ff5ff]">
              {formatUsageDate(peakPoint.usage_date)} · {formatCompactNumber(peakPoint.total_tokens)} tokens
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function QuotaRing({ percentage }: { percentage: number }) {
  const radius = 62;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(percentage, 100));
  const offset = circumference * (1 - clamped / 100);

  return (
    <div className="rounded-[14px] bg-[rgba(18,21,30,0.82)] px-5 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="text-[10px] uppercase tracking-[0.22em] text-[rgba(170,170,179,0.68)]">
        Quota Utilization
      </div>
      <div className="mt-5 flex flex-col items-center">
        <div className="relative h-[11rem] w-[11rem]">
          <svg viewBox="0 0 180 180" className="h-full w-full -rotate-90">
            <circle cx="90" cy="90" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="12" />
            <circle
              cx="90"
              cy="90"
              r={radius}
              fill="none"
              stroke="#a57cff"
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div className="text-[38px] font-semibold tracking-[-0.05em] text-white">{Math.round(clamped)}%</div>
            <div className="mt-1 text-[9px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.62)]">
              Capacity
            </div>
          </div>
        </div>
        <div className="mt-1 text-center">
          <div className="text-[23px] font-semibold tracking-[-0.04em] text-white">1.5M / 2.0M</div>
          <div className="text-[9px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.62)]">
            Tokens used this period
          </div>
        </div>
        <button
          type="button"
          className="mt-5 h-9 w-full rounded-[10px] bg-[rgba(255,255,255,0.06)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(231,231,240,0.88)] transition hover:bg-[rgba(255,255,255,0.1)]"
        >
          Adjust Quota
        </button>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  accent,
  helper,
  icon,
}: {
  label: string;
  value: string;
  accent?: string;
  helper?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-[12px] bg-[rgba(31,34,44,0.78)] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[9px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.68)]">{label}</div>
        <div className="text-[rgba(143,245,255,0.78)]">{icon}</div>
      </div>
      <div className="mt-4 flex items-end gap-2">
        <div className="text-[20px] font-semibold tracking-[-0.04em] text-white">{value}</div>
        {accent ? <div className="mb-1 text-[10px] text-[#8ff5ff]">{accent}</div> : null}
        {helper ? <div className="mb-1 text-[10px] text-[rgba(170,170,179,0.62)]">{helper}</div> : null}
      </div>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === 'completed'
      ? 'bg-[#7af9ff]'
      : status === 'errored'
        ? 'bg-red-400'
        : status === 'interrupted'
          ? 'bg-amber-300'
          : 'bg-[#a57cff]';
  return <span className={`h-2 w-2 rounded-full ${color}`} />;
}

function DashboardWorkspace({
  currentUser,
  onLogout,
  onUserUpdated,
}: {
  currentUser: AuthUser;
  onLogout: () => Promise<void> | void;
  onUserUpdated: (user: AuthUser) => void;
}) {
  const [accountPanelOpen, setAccountPanelOpen] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [dailyPoints, setDailyPoints] = useState<DashboardDailyUsagePoint[]>([]);
  const [rows, setRows] = useState<DashboardLiveTraceRow[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoadState('loading');
      setError('');
      try {
        const [summaryPayload, dailyPayload, tracesPayload] = await Promise.all([
          fetchDashboardSummary(),
          fetchDashboardDailyUsage(),
          fetchDashboardLiveTraces(8),
        ]);
        if (cancelled) return;
        setSummary(summaryPayload);
        setDailyPoints(dailyPayload.points);
        setRows(tracesPayload.rows);
        setLoadState('success');
      } catch (dashboardError) {
        if (cancelled) return;
        setError(dashboardError instanceof Error ? dashboardError.message : 'Unknown error');
        setLoadState('error');
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const quotaRatio = summary
    ? Math.min((summary.total_tokens / 2_000_000) * 100, 100)
    : 0;
  return (
    <main className="min-h-screen bg-[var(--oa-bg)] text-[var(--oa-copy)]">
      {accountPanelOpen ? (
        <AccountDrawer
          user={currentUser}
          onClose={() => setAccountPanelOpen(false)}
          onLogout={onLogout}
          onUserUpdated={onUserUpdated}
        />
      ) : null}

      <div className="mx-auto flex min-h-screen w-full max-w-[1280px] flex-col px-8 pb-10 pt-0">
        <WorkspaceTopNav
          activeSection="dashboard"
          currentUser={currentUser}
          onOpenAccountDrawer={() => setAccountPanelOpen(true)}
        />

        {loadState === 'loading' ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="flex items-center gap-3 rounded-[16px] bg-[rgba(20,23,31,0.82)] px-5 py-4 text-sm text-[rgba(231,231,240,0.88)]">
              <Loader2 size={16} className="animate-spin text-[#63f4ff]" />
              Loading dashboard telemetry...
            </div>
          </div>
        ) : null}

        {loadState === 'error' ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="max-w-md rounded-[16px] border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-200">
              {error}
            </div>
          </div>
        ) : null}

        {loadState === 'success' && summary ? (
          <div className="flex-1 bg-[rgba(8,11,18,0.84)] px-5 py-5">
            <div className="mb-7">
              <h1 className="font-[var(--font-display)] text-[36px] font-bold tracking-[-0.06em] text-white">
                OrchAgent Monitor
              </h1>
              <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-[#63f4ff]">
                <span className="h-2 w-2 rounded-full bg-[#63f4ff]" />
                Live data stream
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Total API Calls"
                value={formatFullNumber(summary.total_llm_calls)}
                helper={`${summary.total_turns} tracked turns`}
                icon={<Activity size={14} />}
              />
              <MetricCard
                label="Total Tokens"
                value={formatFullNumber(summary.total_tokens)}
                helper={formatTokenBreakdown(summary)}
                icon={<ShieldCheck size={14} />}
              />
              <MetricCard
                label="Avg Latency"
                value={formatLatency(summary.avg_latency_ms)}
                helper={`TTFT ${formatLatency(summary.avg_ttft_ms)}`}
                icon={<Activity size={14} />}
              />
              <MetricCard
                label="Total Inference Cost"
                value={formatInferenceCost(summary)}
                helper={
                  summary.estimated_reasoning_cost_microusd > 0
                    ? 'Estimated'
                    : 'Exact'
                }
                icon={<Wallet size={14} />}
              />
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_13rem]">
              <TokenUsageChart points={dailyPoints} />
              <QuotaRing percentage={quotaRatio} />
            </div>

            <section className="mt-4 rounded-[14px] bg-[rgba(18,21,30,0.82)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
              <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.04)] px-5 py-4">
                <div className="font-[var(--font-display)] text-[16px] font-semibold text-white">
                  Real-time Service Trace
                </div>
                <div className="flex items-center gap-2">
                  <button type="button" className="rounded-[8px] bg-[rgba(255,255,255,0.05)] px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[rgba(231,231,240,0.78)]">
                    Export CSV
                  </button>
                  <button type="button" className="rounded-[8px] bg-[rgba(255,255,255,0.05)] px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[rgba(231,231,240,0.78)]">
                    Filter
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full text-left">
                  <thead className="text-[9px] uppercase tracking-[0.14em] text-[rgba(170,170,179,0.62)]">
                    <tr>
                      <th className="px-5 py-3 font-medium">Timestamp</th>
                      <th className="px-4 py-3 font-medium">User ID</th>
                      <th className="px-4 py-3 font-medium">Model</th>
                      <th className="px-4 py-3 font-medium">Tokens</th>
                      <th className="px-4 py-3 font-medium">Latency</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="text-[11px] text-[rgba(231,231,240,0.84)]">
                    {rows.map((row) => (
                      <tr key={row.turn_id} className="border-t border-[rgba(255,255,255,0.04)]">
                        <td className="px-5 py-3 font-mono text-[10px] text-[rgba(170,170,179,0.84)]">
                          {new Date(row.timestamp).toISOString().replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="px-4 py-3">{row.user_id}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-[4px] bg-[rgba(99,244,255,0.12)] px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-[#8ff5ff]">
                            {row.model || 'n/a'}
                          </span>
                        </td>
                        <td className="px-4 py-3">{formatCompactNumber(row.input_tokens + row.output_tokens)}</td>
                        <td className="px-4 py-3">{formatLatency(row.latency_ms)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <StatusDot status={row.status} />
                            <span className="capitalize">{row.status}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="border-t border-[rgba(255,255,255,0.04)] px-5 py-3 text-center text-[9px] font-semibold uppercase tracking-[0.16em] text-[rgba(170,170,179,0.62)]">
                Load previous samples
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}

function DashboardLoadingScreen({ message }: { message: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 px-8 py-7 shadow-2xl shadow-black/40 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Loader2 size={18} className="animate-spin text-blue-400" />
          <span className="text-sm text-slate-300">{message}</span>
        </div>
      </div>
    </main>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, loading, updateUser, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [loading, router, user]);

  if (loading) {
    return <DashboardLoadingScreen message="Restoring dashboard access..." />;
  }

  if (!user) {
    return <DashboardLoadingScreen message="Redirecting to login..." />;
  }

  if (user.must_change_password) {
    router.replace('/');
    return <DashboardLoadingScreen message="Redirecting to password update..." />;
  }

  return (
    <DashboardWorkspace
      currentUser={user}
      onLogout={async () => {
        await logout();
        router.replace('/login');
      }}
      onUserUpdated={updateUser}
    />
  );
}
