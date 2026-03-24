import { BrainCircuit } from 'lucide-react';

export function ReasoningSummaryPanel({
  content,
  isThinking,
  historicalView,
}: {
  content: string;
  isThinking: boolean;
  historicalView: boolean;
}) {
  const hasContent = Boolean(content.trim());

  return (
    <section className="rounded-[12px] border border-[rgba(143,245,255,0.1)] bg-[rgba(35,38,46,0.4)] px-6 py-6 backdrop-blur-md">
      <div className="mb-4 flex items-center gap-3">
        <div className="rounded-[4px] bg-[rgba(143,245,255,0.1)] p-2 text-[#8ff5ff]">
          <BrainCircuit size={15} />
        </div>
        <div>
          <h3 className="font-[var(--font-display)] text-[14px] font-bold text-[#e7e7f0]">
            Inner Monologue
          </h3>
          <p className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.7)]">
            {isThinking ? 'Reasoning Summary Live' : historicalView ? 'Saved Summary' : 'Reasoning Summary'}
          </p>
        </div>
      </div>

      {hasContent ? (
        <div className="space-y-3">
          <div className="rounded-[8px] border-l-2 border-[rgba(172,137,255,0.5)] bg-[rgba(29,31,40,0.55)] px-4 py-3 text-[13px] leading-7 text-[rgba(231,231,240,0.88)]">
            <div className="whitespace-pre-wrap">
              {content}
              {isThinking ? (
                <span className="ml-1 inline-block h-3 w-1.5 animate-pulse rounded-full bg-[#8ff5ff]" />
              ) : null}
            </div>
          </div>
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
