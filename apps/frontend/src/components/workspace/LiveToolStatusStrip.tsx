import { CheckCircle2, Loader2, Terminal, XCircle } from 'lucide-react';

import type { ToolExecution } from '@/types/agent';

function truncateLabel(label: string, limit = 44) {
  if (label.length <= limit) {
    return label;
  }

  return `${label.slice(0, Math.max(limit - 3, 1)).trimEnd()}...`;
}

function toStatusLabel(tool: ToolExecution) {
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
}: {
  toolExecutions: ToolExecution[];
}) {
  const items = toRecentItems(toolExecutions);

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-[14px] border border-[rgba(143,245,255,0.08)] bg-[rgba(35,38,46,0.26)] px-3.5 py-2.5">
      {items.map((tool) => {
        const isRunning = tool.status === 'running';
        const isSuccess = tool.status === 'success';
        const isError = tool.status === 'error';

        return (
          <div
            key={tool.id}
            className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(143,245,255,0.78)]"
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
              {truncateLabel(`${toStatusLabel(tool)} ${tool.name}`)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
