import { CheckCircle2, Loader2, Terminal, XCircle } from 'lucide-react';

import type { ToolExecution } from '@/types/agent';

function truncateLabel(label: string, limit = 44) {
  if (label.length <= limit) {
    return label;
  }

  return `${label.slice(0, Math.max(limit - 3, 1)).trimEnd()}...`;
}

const CODING_TOOL_COPY: Record<string, { running: string; success: string; error: string }> = {
  apply_patch_edit: {
    running: 'Applying patch',
    success: 'Patch applied',
    error: 'Patch failed',
  },
  create_repo_file: {
    running: 'Creating file',
    success: 'File created',
    error: 'Create failed',
  },
  run_repo_command: {
    running: 'Running command',
    success: 'Command done',
    error: 'Command failed',
  },
  verify_local_page: {
    running: 'Verifying page',
    success: 'Page verified',
    error: 'Verify failed',
  },
  search_repo: { running: 'Searching repo', success: 'Search done', error: 'Search failed' },
  read_repo_file: { running: 'Reading file', success: 'File read', error: 'Read failed' },
  list_repo_tree: { running: 'Listing tree', success: 'Tree listed', error: 'List failed' },
  git_status: { running: 'git status', success: 'git status done', error: 'git status failed' },
  git_diff: { running: 'git diff', success: 'git diff done', error: 'git diff failed' },
  git_log: { running: 'git log', success: 'git log done', error: 'git log failed' },
};

function resolveCodingKey(tool: ToolExecution): string | null {
  if (tool.toolName && CODING_TOOL_COPY[tool.toolName]) return tool.toolName;
  if (CODING_TOOL_COPY[tool.name]) return tool.name;
  return null;
}

function toStatusLabel(tool: ToolExecution) {
  const codingKey = resolveCodingKey(tool);
  if (codingKey) {
    const coding = CODING_TOOL_COPY[codingKey];
    if (tool.status === 'running') return coding.running;
    if (tool.status === 'success') return coding.success;
    if (tool.status === 'error') return coding.error;
  }
  if (tool.status === 'running') {
    return 'Executing';
  }
  if (tool.status === 'success') {
    return 'Completed';
  }
  if (tool.status === 'error') {
    return 'Failed';
  }
  return 'Queued';
}

function formatToolLine(tool: ToolExecution): string {
  const label = toStatusLabel(tool);
  // coding tool labels already describe the action, so append tool name only for generic tools.
  if (resolveCodingKey(tool)) {
    return label;
  }
  return `${label} ${tool.name}`;
}

function toRecentItems(toolExecutions: ToolExecution[]) {
  return [...toolExecutions]
    .sort((left, right) => {
      const leftTime = left.endTime ?? left.startTime;
      const rightTime = right.endTime ?? right.startTime;
      return rightTime - leftTime;
    })
    .slice(0, 3);
}

export function LiveToolStatusStrip({
  toolExecutions,
  currentNode,
  loading,
}: {
  toolExecutions: ToolExecution[];
  currentNode?: string;
  loading?: boolean;
}) {
  const items = toRecentItems(toolExecutions);

  const fallbackLabel =
    currentNode && loading ? `Processing ${currentNode}` : currentNode ? `Completed ${currentNode}` : '';
  const hasFallback = Boolean(fallbackLabel) && items.length === 0;
  if (items.length === 0 && !hasFallback) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-[14px] border border-[rgba(143,245,255,0.08)] bg-[rgba(35,38,46,0.26)] px-3.5 py-2.5">
      {hasFallback ? (
        <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(143,245,255,0.78)]">
          {loading ? (
            <Loader2 size={10} className="shrink-0 animate-spin text-[#8ff5ff]" />
          ) : (
            <CheckCircle2 size={10} className="shrink-0 text-emerald-300" />
          )}
          <span className="truncate">{truncateLabel(fallbackLabel)}</span>
        </div>
      ) : null}
      {items.map((tool) => {
        const isRunning = tool.status === 'running';
        const isSuccess = tool.status === 'success';
        const isError = tool.status === 'error';

        return (
          <div
            key={tool.id}
            className={`flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(143,245,255,0.78)] ${isRunning ? 'animate-pulse' : ''}`}
          >
            {isRunning ? (
              <Loader2 size={10} className="shrink-0 animate-spin text-[#8ff5ff]" />
            ) : null}
            {isSuccess ? (
              <CheckCircle2 size={10} className="shrink-0 text-emerald-300" />
            ) : null}
            {isError ? (
              <XCircle size={10} className="shrink-0 text-red-300" />
            ) : null}
            {!isRunning && !isSuccess && !isError ? (
              <Terminal size={10} className="shrink-0 text-slate-400" />
            ) : null}
            <span className="truncate">
              {truncateLabel(formatToolLine(tool))}
            </span>
          </div>
        );
      })}
    </div>
  );
}
