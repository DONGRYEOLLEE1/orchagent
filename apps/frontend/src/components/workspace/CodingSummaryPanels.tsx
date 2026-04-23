import { ShieldCheck, Workflow } from 'lucide-react';
import type { CodingSummary, VerificationStatus } from '@/types/coding';

const STATUS_TONE: Record<string, string> = {
  passed: 'bg-[rgba(143,245,255,0.14)] text-[#8ff5ff]',
  failed: 'bg-[rgba(255,155,155,0.18)] text-[#ff9b9b]',
  skipped: 'bg-[rgba(172,137,255,0.16)] text-[#ac89ff]',
  unverified: 'bg-[rgba(170,170,179,0.18)] text-[rgba(231,231,240,0.76)]',
};

function statusTone(status: VerificationStatus): string {
  return STATUS_TONE[status] || STATUS_TONE.unverified;
}

function EmptyCopy({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-3 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
      {children}
    </div>
  );
}

function CardShell({
  icon,
  title,
  caption,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <section
      data-testid={`coding-${title.toLowerCase().replace(/\s+/g, '-')}-card`}
      className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-6 py-6 backdrop-blur-md"
    >
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-[4px] bg-[rgba(143,245,255,0.14)] p-2 text-[#8ff5ff]">
          {icon}
        </div>
        <div>
          <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
            {title}
          </h3>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.76)]">
            {caption}
          </p>
        </div>
      </div>
      {children}
    </section>
  );
}

export function VerificationStatusCard({ summary }: { summary: CodingSummary | null }) {
  const results = summary?.verification_results ?? [];
  const failure = summary?.failure_summary?.trim();
  if (results.length === 0 && !failure) return null;
  return (
    <CardShell
      icon={<ShieldCheck size={15} />}
      title="Verification"
      caption={results.length ? `${results.length} check${results.length === 1 ? '' : 's'}` : 'Failure reported'}
    >
      {results.length > 0 ? (
        <ul className="space-y-2 text-[12px] leading-6 text-[rgba(231,231,240,0.88)]">
          {results.map((result, idx) => (
            <li
              key={`${result.kind}-${idx}`}
              className="rounded-[8px] border-l-2 border-[rgba(172,137,255,0.4)] bg-[rgba(29,31,40,0.55)] px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="truncate text-[12px] font-semibold">{result.label}</div>
                <span
                  className={`shrink-0 rounded-[4px] px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] ${statusTone(result.status)}`}
                >
                  {result.status}
                </span>
              </div>
              {result.summary ? (
                <p className="mt-1 text-[11px] leading-5 text-[rgba(170,170,179,0.9)]">
                  {result.summary}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {failure ? (
        <p className="mt-3 rounded-[6px] bg-[rgba(255,155,155,0.12)] px-3 py-2 text-[11px] leading-5 text-[#ff9b9b]">
          {failure}
        </p>
      ) : null}
    </CardShell>
  );
}

export function ExecutionPolicyCard({ summary }: { summary: CodingSummary | null }) {
  const mode = summary?.permission_mode?.trim() || '';
  const approvalRequired = Boolean(summary?.approval_required);
  const approvalState = summary?.approval_state?.trim() || '';
  const commitSha = summary?.repo_commit_sha?.slice(0, 12);
  const caption = commitSha ? `@${commitSha.slice(0, 8)}` : mode || 'policy';
  return (
    <CardShell
      icon={<Workflow size={15} />}
      title="Execution Policy"
      caption={caption}
    >
      <dl className="grid grid-cols-1 gap-2 text-[12px] leading-6 text-[rgba(231,231,240,0.88)]">
        <div className="flex justify-between gap-4 rounded-[6px] bg-[rgba(29,31,40,0.55)] px-3 py-1.5">
          <dt className="text-[10px] uppercase tracking-[0.18em] text-[rgba(170,170,179,0.76)]">
            Approval
          </dt>
          <dd className="truncate font-mono text-[11px] text-[rgba(231,231,240,0.9)]">
            {approvalRequired
              ? approvalState
                ? `required · ${approvalState}`
                : 'required'
              : 'not required'}
          </dd>
        </div>
        <div className="flex justify-between gap-4 rounded-[6px] bg-[rgba(29,31,40,0.55)] px-3 py-1.5">
          <dt className="text-[10px] uppercase tracking-[0.18em] text-[rgba(170,170,179,0.76)]">
            Commit
          </dt>
          <dd className="truncate font-mono text-[11px] text-[rgba(231,231,240,0.9)]">
            {commitSha || '—'}
          </dd>
        </div>
        <div className="flex justify-between gap-4 rounded-[6px] bg-[rgba(29,31,40,0.55)] px-3 py-1.5">
          <dt className="text-[10px] uppercase tracking-[0.18em] text-[rgba(170,170,179,0.76)]">
            Completed
          </dt>
          <dd className="truncate font-mono text-[11px] text-[rgba(231,231,240,0.9)]">
            {summary?.completed_at
              ? new Date(summary.completed_at).toLocaleString('ko-KR')
              : '—'}
          </dd>
        </div>
      </dl>
    </CardShell>
  );
}

export function hasCodingSignal(summary: CodingSummary | null | undefined): boolean {
  if (!summary) return false;
  return Boolean(
    summary.workspace_job_id ||
      summary.changed_files.length ||
      summary.verification_results.length ||
      summary.git_status ||
      summary.approval_required
  );
}
