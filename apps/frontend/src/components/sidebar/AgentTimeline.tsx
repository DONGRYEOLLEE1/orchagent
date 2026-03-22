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
      <section className="rounded-2xl border border-slate-800/70 bg-slate-900/40 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
          <Activity size={16} className="text-blue-400" />
          <span>Agent Timeline</span>
        </div>

        <div className="rounded-xl border border-dashed border-slate-800 bg-black/10 px-3 py-4 text-xs leading-5 text-slate-500">
          Historical timeline replay is not restored in v1. The session card still shows
          the latest status, checkpoint, and last activity time for this thread.
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-800/70 bg-slate-900/40 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
        <Activity size={16} className="text-blue-400" />
        <span>Agent Timeline</span>
      </div>

      <div className="max-h-56 space-y-3 overflow-y-auto pr-1">
        {history.length === 0 && !currentNode ? (
          <div className="rounded-xl border border-dashed border-slate-800 bg-black/10 px-3 py-4 text-xs text-slate-500">
            Timeline appears once orchestration starts.
          </div>
        ) : null}

        {history.map((node, index) => (
          <div key={`${node}-${index}`} className="flex items-center gap-3 text-sm text-slate-300">
            <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />
            <span>{node}</span>
          </div>
        ))}

        {currentNode && loading ? (
          <div className="flex items-center gap-3 text-sm font-medium text-blue-300">
            <Loader2 size={14} className="shrink-0 animate-spin" />
            <span>{currentNode} (Running...)</span>
          </div>
        ) : null}

        {currentNode && !loading ? (
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />
            <span>{currentNode}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
