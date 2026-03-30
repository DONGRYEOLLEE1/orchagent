"use client";

import { useEffect, useMemo, useState } from 'react';
import { BrainCircuit, Loader2, MoreHorizontal, Trash2 } from 'lucide-react';

import { deletePersonalMemory, fetchMemorySettings, fetchPersonalMemories, patchMemorySettings } from '@/lib/api';
import type { PersonalMemoryEntry, UserMemorySettings } from '@/types/memory';

function formatSavedAt(value: string) {
  const parts = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}년 ${values.month}월 ${values.day}일에 저장되었음`;
}

function sourceLabel(sourceType: string) {
  if (sourceType === 'explicit') return 'Manual';
  if (sourceType === 'inferred') return 'Auto';
  return sourceType;
}

function PersonalMemoryCard({
  memory,
  deleting,
  onDelete,
}: {
  memory: PersonalMemoryEntry;
  deleting: boolean;
  onDelete: (memoryId: string) => Promise<void> | void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <article className="group relative rounded-[22px] border border-[rgba(255,255,255,0.06)] bg-[rgba(17,21,31,0.72)] px-5 py-5 transition hover:border-[rgba(143,245,255,0.16)] hover:bg-[rgba(20,25,36,0.86)]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex rounded-full border border-[rgba(143,245,255,0.16)] bg-[rgba(143,245,255,0.06)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8ff5ff]">
              {memory.category.replace(/_/g, ' ')}
            </span>
            <span className="inline-flex rounded-full border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.03)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[rgba(170,170,179,0.72)]">
              {sourceLabel(memory.source_type)}
            </span>
          </div>
          <h3 className="mt-4 text-[19px] font-semibold tracking-[-0.03em] text-white">
            {memory.title}
          </h3>
          <p className="mt-2 max-w-[52rem] text-[14px] leading-7 text-[rgba(170,170,179,0.82)]">
            {memory.content_text}
          </p>
        </div>

        <div className="relative shrink-0">
          <button
            type="button"
            aria-label={`Memory actions ${memory.title}`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((previous) => !previous)}
            className={[
              'rounded-[10px] p-2 text-[rgba(170,170,179,0.72)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]',
              menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
            ].join(' ')}
          >
            <MoreHorizontal size={16} />
          </button>

          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 top-11 z-10 flex w-[220px] flex-col rounded-[16px] border border-[rgba(255,255,255,0.06)] bg-[rgba(9,12,18,0.96)] p-2 shadow-2xl shadow-black/45 backdrop-blur-xl"
            >
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  void onDelete(memory.id);
                }}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2 text-left text-sm text-red-200 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                <span>삭제</span>
              </button>
              <div className="mt-2 border-t border-[rgba(255,255,255,0.06)] px-3 pt-3 text-[11px] leading-5 text-[rgba(170,170,179,0.72)]">
                {formatSavedAt(memory.created_at)}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export function PersonalMemoryPanel() {
  const [settings, setSettings] = useState<UserMemorySettings | null>(null);
  const [memories, setMemories] = useState<PersonalMemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [deletingId, setDeletingId] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [loadedSettings, loadedMemories] = await Promise.all([
        fetchMemorySettings(),
        fetchPersonalMemories(),
      ]);
      setSettings(loadedSettings);
      setMemories(loadedMemories);
    } catch (memoryError) {
      setError(memoryError instanceof Error ? memoryError.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const sortedMemories = useMemo(
    () => [...memories].sort((left, right) => right.created_at.localeCompare(left.created_at)),
    [memories]
  );

  const toggleMemory = async (nextEnabled: boolean) => {
    setSavingSettings(true);
    setError('');
    try {
      const updated = await patchMemorySettings({ memoryEnabled: nextEnabled });
      setSettings(updated);
    } catch (memoryError) {
      setError(memoryError instanceof Error ? memoryError.message : 'Unknown error');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleDelete = async (memoryId: string) => {
    setDeletingId(memoryId);
    setError('');
    try {
      await deletePersonalMemory(memoryId);
      setMemories((previous) => previous.filter((memory) => memory.id !== memoryId));
    } catch (memoryError) {
      setError(memoryError instanceof Error ? memoryError.message : 'Unknown error');
    } finally {
      setDeletingId('');
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[18rem] items-center justify-center rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(17,21,31,0.62)]">
        <div className="flex items-center gap-3 text-[14px] text-[rgba(170,170,179,0.78)]">
          <Loader2 size={18} className="animate-spin text-[#8ff5ff]" />
          <span>Loading personal memory...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(18,22,32,0.76)] px-5 py-5">
          <div className="flex items-start gap-3">
            <span className="inline-flex rounded-[14px] bg-[rgba(0,240,255,0.08)] p-2 text-[#8ff5ff]">
              <BrainCircuit size={16} />
            </span>
            <div>
              <h2 className="text-[18px] font-semibold text-white">Personal Memory</h2>
              <p className="mt-1 text-[13px] leading-6 text-[rgba(170,170,179,0.76)]">
                Durable preferences extracted from your requests are stored here and reused to personalize future replies.
              </p>
            </div>
          </div>
        </div>

        <section className="rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(18,22,32,0.76)] px-5 py-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(143,245,255,0.72)]">
            Memory Policy
          </div>
          <div className="mt-3 flex items-start justify-between gap-4">
            <div>
              <div className="text-[15px] font-semibold text-white">Enable memory</div>
              <div className="mt-1 text-[12px] leading-6 text-[rgba(170,170,179,0.72)]">
                When enabled, future answers can reuse saved preferences and stable interests.
              </div>
            </div>

            <button
              type="button"
              aria-label="Enable memory policy"
              aria-pressed={settings?.memory_enabled}
              onClick={() => void toggleMemory(!(settings?.memory_enabled ?? true))}
              disabled={savingSettings}
              className={[
                'relative inline-flex h-7 w-14 shrink-0 rounded-full transition',
                settings?.memory_enabled ? 'bg-[#00d7e5]' : 'bg-[rgba(255,255,255,0.16)]',
              ].join(' ')}
            >
              <span
                className={[
                  'absolute top-1 h-5 w-5 rounded-full bg-white transition',
                  settings?.memory_enabled ? 'left-8' : 'left-1',
                ].join(' ')}
              />
            </button>
          </div>
        </section>
      </section>

      {error ? (
        <div className="rounded-[18px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <section className="space-y-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(143,245,255,0.72)]">
            Saved Memory
          </div>
          <h3 className="mt-2 text-[24px] font-semibold tracking-[-0.04em] text-white">
            Stored preference notes
          </h3>
        </div>

        {sortedMemories.length === 0 ? (
          <section className="rounded-[24px] border border-dashed border-[rgba(255,255,255,0.1)] bg-[rgba(17,21,31,0.42)] px-6 py-10 text-center">
            <div className="mx-auto max-w-[32rem]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(143,245,255,0.72)]">
                Empty State
              </div>
              <h3 className="mt-3 text-[24px] font-semibold tracking-[-0.04em] text-white">
                No saved personal memory yet
              </h3>
              <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.76)]">
                When a request clearly includes a stable preference or tendency, the memory agent will normalize it and surface it here.
              </p>
            </div>
          </section>
        ) : (
          <div className="space-y-4">
            {sortedMemories.map((memory) => (
              <PersonalMemoryCard
                key={memory.id}
                memory={memory}
                deleting={deletingId === memory.id}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
