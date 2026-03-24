import { Sparkles } from 'lucide-react';

export type SuggestedQueriesLoadState = 'idle' | 'loading' | 'success' | 'error';

export function SuggestedQueriesPanel({
  queries,
  loadState,
  onSelectQuery,
  historicalView,
}: {
  queries: string[];
  loadState: SuggestedQueriesLoadState;
  onSelectQuery?: (query: string) => void;
  historicalView: boolean;
}) {
  return (
    <section className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-5 py-5 backdrop-blur-md">
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-[4px] bg-[rgba(143,245,255,0.1)] p-2 text-[#8ff5ff]">
          <Sparkles size={15} />
        </div>
        <div>
          <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
            Suggested Queries
          </h3>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.7)]">
            Follow-up prompts
          </p>
        </div>
      </div>

      {loadState === 'loading' ? (
        <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
          Generating follow-up prompts from the latest turn...
        </div>
      ) : null}

      {loadState !== 'loading' && queries.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {queries.map((query) => (
            <button
              key={query}
              type="button"
              onClick={() => onSelectQuery?.(query)}
              className="rounded-[10px] border border-[rgba(255,255,255,0.04)] bg-[rgba(35,38,46,0.52)] px-3 py-2.5 text-left text-[10px] leading-4 text-[rgba(231,231,240,0.86)] transition hover:border-[rgba(143,245,255,0.22)] hover:bg-[rgba(35,38,46,0.66)] hover:text-[#e7e7f0]"
            >
              {query}
            </button>
          ))}
        </div>
      ) : null}

      {loadState !== 'loading' && queries.length === 0 ? (
        <div className="rounded-[8px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
          {historicalView
            ? 'Saved follow-up recommendations will appear here when telemetry has been generated for this thread.'
            : 'Follow-up prompt recommendations appear after the active answer finishes streaming.'}
        </div>
      ) : null}
    </section>
  );
}
