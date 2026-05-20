import { useMemo, useState } from 'react';
import { FolderTree, ChevronRight, FileCode } from 'lucide-react';
import type { CodingSummary, DiffSnippet, FileEntry } from '@/types/coding';

const STATUS_COLOR: Record<string, string> = {
  M: 'text-[#ac89ff]',
  A: 'text-[#8ff5ff]',
  D: 'text-[#ff9b9b]',
  R: 'text-[#ffd680]',
  '?': 'text-[rgba(170,170,179,0.78)]',
};

function statusTone(status?: string | null): string {
  if (!status) return 'text-[rgba(231,231,240,0.88)]';
  return STATUS_COLOR[status] || 'text-[#ac89ff]';
}

function indentFor(path: string): number {
  // depth by `/` count, bounded to 4 levels of visible indent
  const depth = Math.min(path.split('/').length - 1, 4);
  return depth * 10;
}

function DiffBody({ diff }: { diff: DiffSnippet | null | undefined }) {
  if (!diff) {
    return (
      <p className="mt-2 px-3 py-2 text-[11px] italic text-[rgba(170,170,179,0.7)]">
        No diff captured for this file.
      </p>
    );
  }
  const lines = diff.unified_diff.split('\n');
  return (
    <div className="mt-2 overflow-x-auto rounded-[6px] bg-[rgba(10,12,18,0.72)] px-3 py-2 font-mono text-[11px] leading-5">
      {lines.map((line, idx) => {
        let color = 'text-[rgba(170,170,179,0.9)]';
        if (line.startsWith('+') && !line.startsWith('+++')) color = 'text-[#8fffb1]';
        else if (line.startsWith('-') && !line.startsWith('---')) color = 'text-[#ff9b9b]';
        else if (line.startsWith('@@')) color = 'text-[#8ff5ff]';
        else if (line.startsWith('diff --git') || line.startsWith('index ')) color = 'text-[rgba(172,137,255,0.82)]';
        return (
          <pre key={idx} className={`whitespace-pre ${color}`}>
            {line || ' '}
          </pre>
        );
      })}
      {diff.truncated ? (
        <p className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[rgba(255,155,155,0.82)]">
          ... diff truncated (per-file 4KB cap)
        </p>
      ) : null}
    </div>
  );
}

function TreeRow({
  entry,
  diff,
  expanded,
  onToggle,
}: {
  entry: FileEntry;
  diff?: DiffSnippet | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasDiff = Boolean(diff);
  const isDir = entry.kind === 'dir';
  const clickable = !isDir && entry.changed_status;
  const displayName = entry.path.split('/').pop() || entry.path;
  return (
    <div>
      <button
        type="button"
        onClick={clickable ? onToggle : undefined}
        aria-expanded={clickable ? expanded : undefined}
        disabled={!clickable}
        className={`flex w-full items-center gap-2 rounded-[6px] px-2 py-1 text-[12px] leading-5 transition ${
          clickable
            ? 'cursor-pointer hover:bg-[rgba(143,245,255,0.08)]'
            : 'cursor-default'
        }`}
        style={{ paddingLeft: indentFor(entry.path) + 8 }}
      >
        {clickable ? (
          <ChevronRight
            size={11}
            className={`shrink-0 text-[rgba(170,170,179,0.78)] transition ${expanded ? 'rotate-90' : ''}`}
          />
        ) : (
          <span className="inline-block w-[11px]" aria-hidden />
        )}
        {isDir ? (
          <FolderTree size={12} className="shrink-0 text-[rgba(143,245,255,0.62)]" />
        ) : (
          <FileCode size={12} className="shrink-0 text-[rgba(170,170,179,0.62)]" />
        )}
        <span className={`truncate font-mono ${statusTone(entry.changed_status)}`}>
          {displayName}
        </span>
        {entry.changed_status ? (
          <span
            className={`ml-auto shrink-0 rounded-[4px] bg-[rgba(172,137,255,0.16)] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] ${statusTone(entry.changed_status)}`}
          >
            {entry.changed_status}
          </span>
        ) : null}
        {!entry.changed_status && hasDiff ? (
          <span className="ml-auto shrink-0 text-[10px] uppercase tracking-[0.12em] text-[rgba(170,170,179,0.52)]">
            diff
          </span>
        ) : null}
      </button>
      {clickable && expanded ? <DiffBody diff={diff} /> : null}
    </div>
  );
}

export function RepoTreePanel({ summary }: { summary: CodingSummary | null | undefined }) {
  const tree = summary?.tree ?? [];
  // Phase 3.5 — derive ``diffs`` and the indexed lookup inside the same
  // useMemo so the dependency list is the stable ``summary?.diffs`` reference
  // instead of a freshly-allocated [] on every render.
  const diffByPath = useMemo(() => {
    const diffs = summary?.diffs ?? [];
    const m: Record<string, DiffSnippet> = {};
    for (const d of diffs) m[d.path] = d;
    return m;
  }, [summary?.diffs]);

  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const changedCount = tree.filter((e) => e.changed_status).length;

  return (
    <section
      data-testid="coding-repo-tree-card"
      className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-4 py-3 backdrop-blur-md"
    >
      <div className="mb-3 flex items-center gap-3">
        <div className="rounded-[4px] bg-[rgba(143,245,255,0.14)] p-1.5 text-[#8ff5ff]">
          <FolderTree size={13} />
        </div>
        <div>
          <h3 className="font-[var(--font-display)] text-[13px] font-bold text-[#e7e7f0]">
            Workspace
          </h3>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.76)]">
            {tree.length
              ? `${tree.length} entries · ${changedCount} changed`
              : 'No captured tree'}
          </p>
        </div>
      </div>
      {tree.length > 0 ? (
        <div className="space-y-1">
          {tree.map((entry) => (
            <TreeRow
              key={`${entry.kind}:${entry.path}`}
              entry={entry}
              diff={diffByPath[entry.path]}
              expanded={!!expanded[entry.path]}
              onToggle={() =>
                setExpanded((prev) => ({
                  ...prev,
                  [entry.path]: !prev[entry.path],
                }))
              }
            />
          ))}
        </div>
      ) : (
        <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-3 py-3 text-[11px] leading-5 text-[rgba(170,170,179,0.78)]">
          Run a coding task and the workspace tree will appear here. Changed files become clickable
          to inspect their diff inline.
        </div>
      )}
    </section>
  );
}
