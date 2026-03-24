import { Activity, CheckCircle2, Loader2 } from 'lucide-react';

export function AgentTimeline({
  history,
  currentNode,
  loading,
  historicalView,
}: {
  history: string[];
  currentNode: string;
  loading: boolean;
  historicalView: boolean;
}) {
  if (historicalView) {
    return (
      <section className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-6 py-6 backdrop-blur-md">
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-[4px] bg-[rgba(143,245,255,0.1)] p-2 text-[#8ff5ff]">
            <Activity size={15} />
          </div>
          <div>
            <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
              Agent Timeline
            </h3>
            <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.7)]">
              Historical view
            </p>
          </div>
        </div>

        <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
          Historical timeline replay is not restored in v1. Full tool-by-tool replay is still unavailable for saved threads.
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-6 py-6 backdrop-blur-md">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="rounded-[4px] bg-[rgba(143,245,255,0.1)] p-2 text-[#8ff5ff]">
            <Activity size={15} />
          </div>
          <div>
            <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
              Agent Timeline
            </h3>
            <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.7)]">
              {loading ? 'Processing' : 'Latest route'}
            </p>
          </div>
        </div>

        <div className="text-[10px] uppercase tracking-[0.22em] text-[rgba(170,170,179,0.7)]">
          {history.length + (currentNode ? 1 : 0)} steps
        </div>
      </div>

      <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
        {history.length === 0 && !currentNode ? (
          <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
            Timeline appears once orchestration starts.
          </div>
        ) : null}

        {history.map((node, index) => (
          <div
            key={`${node}-${index}`}
            className="flex items-center gap-3 rounded-[8px] border border-[rgba(255,255,255,0.04)] bg-[rgba(29,31,40,0.32)] px-3 py-3 text-[13px] text-[rgba(231,231,240,0.84)]"
          >
            <CheckCircle2 size={14} className="shrink-0 text-emerald-300" />
            <span>{node}</span>
          </div>
        ))}

        {currentNode && loading ? (
          <div className="flex items-center gap-3 rounded-[8px] border border-[rgba(143,245,255,0.16)] bg-[rgba(29,31,40,0.4)] px-3 py-3 text-[13px] font-medium text-[#8ff5ff]">
            <Loader2 size={14} className="shrink-0 animate-spin" />
            <span>{currentNode} (Running...)</span>
          </div>
        ) : null}

        {currentNode && !loading ? (
          <div className="flex items-center gap-3 rounded-[8px] border border-[rgba(255,255,255,0.04)] bg-[rgba(29,31,40,0.32)] px-3 py-3 text-[13px] text-[rgba(231,231,240,0.84)]">
            <CheckCircle2 size={14} className="shrink-0 text-emerald-300" />
            <span>{currentNode}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
