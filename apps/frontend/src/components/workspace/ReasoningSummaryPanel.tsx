import { useMemo, useState } from 'react';
import { BrainCircuit, ChevronDown, ChevronsDown, ChevronsUp } from 'lucide-react';
import type { ReasoningEntry } from '@/types/thread';

export function ReasoningSummaryPanel({
  content,
  entries,
  isThinking,
  historicalView,
  fallbackSummary,
}: {
  content: string;
  entries?: ReasoningEntry[];
  isThinking: boolean;
  historicalView: boolean;
  fallbackSummary?: string;
}) {
  const normalizedEntries = useMemo(() => {
    if (entries && entries.length > 0) {
      return entries;
    }
    const resolved = content.trim() || fallbackSummary || '';
    if (!resolved.trim()) {
      return [];
    }
    return [
      {
        id: historicalView ? 'historical-summary' : 'live-summary',
        displayName: historicalView ? 'Saved Summary' : 'Reasoning Summary',
        content: resolved,
      },
    ];
  }, [content, entries, fallbackSummary, historicalView]);
  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({});
  const [globalCollapsed, setGlobalCollapsed] = useState<boolean | null>(null);
  const resolvedContent = content.trim() || fallbackSummary || '';
  const hasContent = normalizedEntries.length > 0 || Boolean(resolvedContent.trim());

  const resolveCollapsed = (entry: { id: string; content: string }): boolean => {
    if (entry.id in collapseOverrides) {
      return collapseOverrides[entry.id];
    }
    if (globalCollapsed !== null) {
      return globalCollapsed;
    }
    return entry.content.length > 260;
  };

  const toggleEntry = (entryId: string, currentCollapsed: boolean) => {
    setCollapseOverrides((prev) => ({
      ...prev,
      [entryId]: !currentCollapsed,
    }));
  };

  const allCollapsed = normalizedEntries.length > 0 && normalizedEntries.every(resolveCollapsed);
  const showBulkToggle = normalizedEntries.length >= 2;

  const toggleAll = () => {
    const next = !allCollapsed;
    setGlobalCollapsed(next);
    setCollapseOverrides({});
  };

  return (
    <section className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-6 py-6 backdrop-blur-md">
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-[4px] bg-[rgba(172,137,255,0.14)] p-2 text-[#ac89ff]">
          <BrainCircuit size={15} />
        </div>
        <div className="flex-1">
          <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
            Inner Monologue
          </h3>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(172,137,255,0.76)]">
            {isThinking ? 'Reasoning Summary Live' : historicalView ? 'Saved Summary' : 'Reasoning Summary'}
          </p>
        </div>
        {showBulkToggle ? (
          <button
            type="button"
            onClick={toggleAll}
            aria-label={allCollapsed ? 'Expand all reasoning entries' : 'Collapse all reasoning entries'}
            title={allCollapsed ? 'Expand all' : 'Collapse all'}
            className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-[rgba(172,137,255,0.7)] transition hover:bg-[rgba(172,137,255,0.12)] hover:text-[#ac89ff]"
          >
            {allCollapsed ? <ChevronsDown size={14} /> : <ChevronsUp size={14} />}
          </button>
        ) : null}
      </div>

      {hasContent ? (
        <div className="space-y-3">
          {normalizedEntries.map((entry, index) => {
            const isCollapsed = resolveCollapsed(entry);
            const heading = entry.displayName || entry.node || `Reasoning ${index + 1}`;
            return (
              <div
                key={entry.id}
                className="rounded-[8px] border-l-2 border-[rgba(172,137,255,0.5)] bg-[rgba(29,31,40,0.55)] px-4 py-3 text-[13px] leading-7 text-[rgba(231,231,240,0.88)]"
              >
                <button
                  type="button"
                  onClick={() => toggleEntry(entry.id, isCollapsed)}
                  className="flex w-full items-start justify-between gap-3 text-left"
                >
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(172,137,255,0.72)]">
                      {heading}
                    </div>
                    {entry.timestamp ? (
                      <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[rgba(170,170,179,0.62)]">
                        {new Date(entry.timestamp).toLocaleTimeString('ko-KR', {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </div>
                    ) : null}
                  </div>
                  <ChevronDown
                    size={15}
                    className={`mt-1 shrink-0 text-[rgba(172,137,255,0.82)] transition ${
                      isCollapsed ? '-rotate-90' : 'rotate-0'
                    }`}
                  />
                </button>
                {!isCollapsed ? (
                  <div className="mt-3 whitespace-pre-wrap">
                    {entry.content}
                    {isThinking && index === normalizedEntries.length - 1 ? (
                      <span className="ml-1 inline-block h-3 w-1.5 animate-pulse rounded-full bg-[#8ff5ff]" />
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
          {historicalView
            ? 'Historical reasoning summary will appear here when a saved telemetry summary exists for this thread.'
            : 'Reasoning summary appears here while the active turn is being orchestrated.'}
        </div>
      )}
    </section>
  );
}
