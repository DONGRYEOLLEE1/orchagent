import { Brain, Code2 } from 'lucide-react';
import type { RightTab } from '@/types/thread';

interface TabDef {
  id: RightTab;
  label: string;
  icon: React.ReactNode;
}

const TABS: TabDef[] = [
  { id: 'reasoning', label: 'Reasoning', icon: <Brain size={13} /> },
  { id: 'coding', label: 'Coding', icon: <Code2 size={13} /> },
];

export function CodingAsideTabs({
  active,
  codingCount,
  onChange,
}: {
  active: RightTab;
  codingCount?: number;
  onChange: (next: RightTab) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Workspace side panel"
      className="mb-4 flex items-center gap-1 rounded-[10px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.55)] p-1"
    >
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        const showBadge = tab.id === 'coding' && typeof codingCount === 'number' && codingCount > 0;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`aside-panel-${tab.id}`}
            id={`aside-tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-[8px] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] transition ${
              isActive
                ? 'bg-[rgba(143,245,255,0.14)] text-[#8ff5ff]'
                : 'text-[rgba(170,170,179,0.72)] hover:text-[rgba(231,231,240,0.9)]'
            }`}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {showBadge ? (
              <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[rgba(143,245,255,0.22)] px-1 text-[9px] font-bold text-[#8ff5ff]">
                {codingCount}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
