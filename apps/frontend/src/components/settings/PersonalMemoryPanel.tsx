"use client";

import { useEffect, useMemo, useState } from 'react';
import {
  BrainCircuit,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react';

import {
  createPersonalizationInstruction,
  deletePersonalMemory,
  deletePersonalizationInstruction,
  fetchMemorySettings,
  fetchPersonalMemories,
  fetchPersonalizationInstructions,
  fetchPersonalizationSettings,
  patchMemorySettings,
  patchPersonalizationSettings,
  updatePersonalizationInstruction,
} from '@/lib/api';
import type {
  PersonalMemoryEntry,
  PersonalizationInstruction,
  PersonalizationInstructionType,
  UserMemorySettings,
} from '@/types/memory';

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

function instructionTypeLabel(type: PersonalizationInstructionType) {
  if (type === 'response_style') return 'Response Style';
  return 'User Profile';
}

function createInstructionDraft(
  instruction?: PersonalizationInstruction
): {
  mode: 'create' | 'edit';
  instructionId: string;
  instructionType: PersonalizationInstructionType;
  title: string;
  contentText: string;
  enabled: boolean;
} {
  if (!instruction) {
    return {
      mode: 'create',
      instructionId: '',
      instructionType: 'response_style',
      title: '',
      contentText: '',
      enabled: true,
    };
  }

  return {
    mode: 'edit',
    instructionId: instruction.id,
    instructionType: instruction.instruction_type,
    title: instruction.title,
    contentText: instruction.content_text,
    enabled: instruction.enabled,
  };
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

function PersonalizationInstructionCard({
  instruction,
  deleting,
  saving,
  onEdit,
  onDelete,
  onToggle,
}: {
  instruction: PersonalizationInstruction;
  deleting: boolean;
  saving: boolean;
  onEdit: (instruction: PersonalizationInstruction) => void;
  onDelete: (instructionId: string) => Promise<void> | void;
  onToggle: (instruction: PersonalizationInstruction, nextEnabled: boolean) => Promise<void> | void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <article className="group relative rounded-[22px] border border-[rgba(255,255,255,0.06)] bg-[rgba(15,19,28,0.82)] px-5 py-5 transition hover:border-[rgba(255,213,127,0.18)] hover:bg-[rgba(18,24,34,0.94)]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex rounded-full border border-[rgba(255,213,127,0.2)] bg-[rgba(255,213,127,0.08)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#ffd57f]">
              {instructionTypeLabel(instruction.instruction_type)}
            </span>
            <span
              className={[
                'inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em]',
                instruction.enabled
                  ? 'border border-emerald-400/20 bg-emerald-400/10 text-emerald-200'
                  : 'border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.03)] text-[rgba(170,170,179,0.72)]',
              ].join(' ')}
            >
              {instruction.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>

          <h3 className="mt-4 text-[19px] font-semibold tracking-[-0.03em] text-white">
            {instruction.title}
          </h3>
          <p className="mt-2 max-w-[52rem] text-[14px] leading-7 text-[rgba(170,170,179,0.82)]">
            {instruction.content_text}
          </p>
        </div>

        <div className="flex shrink-0 items-start gap-2">
          <button
            type="button"
            aria-label={`${instruction.enabled ? 'Disable' : 'Enable'} instruction ${instruction.title}`}
            onClick={() => void onToggle(instruction, !instruction.enabled)}
            disabled={saving}
            className={[
              'inline-flex min-w-[86px] items-center justify-center rounded-[12px] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] transition',
              instruction.enabled
                ? 'bg-[rgba(255,255,255,0.08)] text-[rgba(231,231,240,0.92)] hover:bg-[rgba(255,255,255,0.12)]'
                : 'bg-[rgba(255,213,127,0.14)] text-[#ffd57f] hover:bg-[rgba(255,213,127,0.2)]',
            ].join(' ')}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : instruction.enabled ? 'Disable' : 'Enable'}
          </button>

          <div className="relative">
            <button
              type="button"
              aria-label={`Instruction actions ${instruction.title}`}
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
                className="absolute right-0 top-11 z-10 flex w-[230px] flex-col rounded-[16px] border border-[rgba(255,255,255,0.06)] bg-[rgba(9,12,18,0.96)] p-2 shadow-2xl shadow-black/45 backdrop-blur-xl"
              >
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onEdit(instruction);
                  }}
                  className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2 text-left text-sm text-[rgba(231,231,240,0.92)] transition hover:bg-[rgba(255,255,255,0.04)]"
                >
                  <Pencil size={14} />
                  <span>편집</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    void onDelete(instruction.id);
                  }}
                  disabled={deleting}
                  className="inline-flex items-center gap-2 rounded-[12px] px-3 py-2 text-left text-sm text-red-200 transition hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  <span>삭제</span>
                </button>
                <div className="mt-2 border-t border-[rgba(255,255,255,0.06)] px-3 pt-3 text-[11px] leading-5 text-[rgba(170,170,179,0.72)]">
                  {formatSavedAt(instruction.created_at)}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

export function PersonalMemoryPanel() {
  const [settings, setSettings] = useState<UserMemorySettings | null>(null);
  const [memories, setMemories] = useState<PersonalMemoryEntry[]>([]);
  const [instructions, setInstructions] = useState<PersonalizationInstruction[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingMemorySettings, setSavingMemorySettings] = useState(false);
  const [savingInstructionSettings, setSavingInstructionSettings] = useState(false);
  const [deletingId, setDeletingId] = useState('');
  const [deletingInstructionId, setDeletingInstructionId] = useState('');
  const [savingInstructionId, setSavingInstructionId] = useState('');
  const [error, setError] = useState('');
  const [composer, setComposer] = useState<ReturnType<typeof createInstructionDraft> | null>(null);
  const [composerError, setComposerError] = useState('');
  const [submittingComposer, setSubmittingComposer] = useState(false);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [
        loadedMemorySettings,
        loadedPersonalizationSettings,
        loadedMemories,
        loadedInstructions,
      ] = await Promise.all([
        fetchMemorySettings(),
        fetchPersonalizationSettings(),
        fetchPersonalMemories(),
        fetchPersonalizationInstructions(),
      ]);
      setSettings({
        ...loadedMemorySettings,
        instructions_enabled: loadedPersonalizationSettings.instructions_enabled,
      });
      setMemories(loadedMemories);
      setInstructions(loadedInstructions);
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

  const sortedInstructions = useMemo(
    () => [...instructions].sort((left, right) => {
      if (left.enabled !== right.enabled) {
        return left.enabled ? -1 : 1;
      }
      return right.updated_at.localeCompare(left.updated_at);
    }),
    [instructions]
  );

  const toggleMemory = async (nextEnabled: boolean) => {
    setSavingMemorySettings(true);
    setError('');
    try {
      const updated = await patchMemorySettings({ memoryEnabled: nextEnabled });
      setSettings((previous) => ({
        ...(previous || updated),
        ...updated,
      }));
    } catch (memoryError) {
      setError(memoryError instanceof Error ? memoryError.message : 'Unknown error');
    } finally {
      setSavingMemorySettings(false);
    }
  };

  const toggleInstructionsPolicy = async (nextEnabled: boolean) => {
    setSavingInstructionSettings(true);
    setError('');
    try {
      const updated = await patchPersonalizationSettings({ instructionsEnabled: nextEnabled });
      setSettings((previous) => ({
        ...(previous || updated),
        ...updated,
      }));
    } catch (instructionError) {
      setError(instructionError instanceof Error ? instructionError.message : 'Unknown error');
    } finally {
      setSavingInstructionSettings(false);
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

  const handleDeleteInstruction = async (instructionId: string) => {
    setDeletingInstructionId(instructionId);
    setError('');
    try {
      await deletePersonalizationInstruction(instructionId);
      setInstructions((previous) => previous.filter((instruction) => instruction.id !== instructionId));
      setComposer((previous) => (previous?.instructionId === instructionId ? null : previous));
    } catch (instructionError) {
      setError(instructionError instanceof Error ? instructionError.message : 'Unknown error');
    } finally {
      setDeletingInstructionId('');
    }
  };

  const handleInstructionToggle = async (
    instruction: PersonalizationInstruction,
    nextEnabled: boolean
  ) => {
    setSavingInstructionId(instruction.id);
    setError('');
    try {
      const updated = await updatePersonalizationInstruction({
        instructionId: instruction.id,
        enabled: nextEnabled,
      });
      setInstructions((previous) =>
        previous.map((item) => (item.id === instruction.id ? updated : item))
      );
      setComposer((previous) =>
        previous?.instructionId === instruction.id
          ? { ...previous, enabled: updated.enabled }
          : previous
      );
    } catch (instructionError) {
      setError(instructionError instanceof Error ? instructionError.message : 'Unknown error');
    } finally {
      setSavingInstructionId('');
    }
  };

  const submitComposer = async () => {
    if (!composer) return;

    const title = composer.title.trim();
    const contentText = composer.contentText.trim();
    if (!title || !contentText) {
      setComposerError('제목과 내용을 모두 입력해 주세요.');
      return;
    }

    setSubmittingComposer(true);
    setComposerError('');
    setError('');
    try {
      if (composer.mode === 'create') {
        const created = await createPersonalizationInstruction({
          instructionType: composer.instructionType,
          title,
          contentText,
          enabled: composer.enabled,
        });
        setInstructions((previous) => [created, ...previous]);
      } else {
        const updated = await updatePersonalizationInstruction({
          instructionId: composer.instructionId,
          instructionType: composer.instructionType,
          title,
          contentText,
          enabled: composer.enabled,
        });
        setInstructions((previous) =>
          previous.map((item) => (item.id === composer.instructionId ? updated : item))
        );
      }
      setComposer(null);
    } catch (instructionError) {
      const message = instructionError instanceof Error ? instructionError.message : 'Unknown error';
      setComposerError(message);
      setError(message);
    } finally {
      setSubmittingComposer(false);
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

        <div className="space-y-4">
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
                disabled={savingMemorySettings}
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

          <section className="rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(18,22,32,0.76)] px-5 py-5">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(255,213,127,0.72)]">
              Instructions Policy
            </div>
            <div className="mt-3 flex items-start justify-between gap-4">
              <div>
                <div className="text-[15px] font-semibold text-white">Enable instructions</div>
                <div className="mt-1 text-[12px] leading-6 text-[rgba(170,170,179,0.72)]">
                  Saved response preferences and profile notes remain editable even when runtime application is paused.
                </div>
              </div>

              <button
                type="button"
                aria-label="Enable instructions policy"
                aria-pressed={settings?.instructions_enabled}
                onClick={() => void toggleInstructionsPolicy(!(settings?.instructions_enabled ?? true))}
                disabled={savingInstructionSettings}
                className={[
                  'relative inline-flex h-7 w-14 shrink-0 rounded-full transition',
                  settings?.instructions_enabled ? 'bg-[#ffd57f]' : 'bg-[rgba(255,255,255,0.16)]',
                ].join(' ')}
              >
                <span
                  className={[
                    'absolute top-1 h-5 w-5 rounded-full bg-white transition',
                    settings?.instructions_enabled ? 'left-8' : 'left-1',
                  ].join(' ')}
                />
              </button>
            </div>
          </section>
        </div>
      </section>

      {error ? (
        <div className="rounded-[18px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(143,245,255,0.72)]">
              Saved Memory
            </div>
            <h3 className="mt-2 text-[24px] font-semibold tracking-[-0.04em] text-white">
              Stored preference notes
            </h3>
          </div>
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

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(255,213,127,0.72)]">
              Personalization Instructions
            </div>
            <h3 className="mt-2 text-[24px] font-semibold tracking-[-0.04em] text-white">
              Explicit defaults you control
            </h3>
            <p className="mt-2 max-w-[40rem] text-[14px] leading-7 text-[rgba(170,170,179,0.76)]">
              These instructions are bounded personalization defaults. The current turn still overrides them when it conflicts.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setComposer(createInstructionDraft());
              setComposerError('');
            }}
            className="inline-flex items-center gap-2 rounded-[14px] bg-[rgba(255,213,127,0.14)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.16em] text-[#ffd57f] transition hover:bg-[rgba(255,213,127,0.2)]"
          >
            <Plus size={14} />
            <span>새 지침 추가</span>
          </button>
        </div>

        {composer ? (
          <section className="rounded-[24px] border border-[rgba(255,213,127,0.16)] bg-[rgba(24,20,12,0.58)] px-5 py-5">
            <div className="flex items-start gap-3">
              <span className="inline-flex rounded-[14px] bg-[rgba(255,213,127,0.1)] p-2 text-[#ffd57f]">
                <Sparkles size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(255,213,127,0.72)]">
                      {composer.mode === 'create' ? 'Create Instruction' : 'Edit Instruction'}
                    </div>
                    <h4 className="mt-2 text-[18px] font-semibold text-white">
                      {composer.mode === 'create' ? 'Add a new personalization rule' : 'Update personalization rule'}
                    </h4>
                  </div>
                </div>

                <div className="mt-5 grid gap-4 md:grid-cols-[180px_minmax(0,1fr)]">
                  <label className="flex flex-col gap-2">
                    <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,213,127,0.68)]">
                      Type
                    </span>
                    <select
                      aria-label="Instruction type"
                      value={composer.instructionType}
                      onChange={(event) =>
                        setComposer((previous) =>
                          previous
                            ? {
                                ...previous,
                                instructionType: event.target.value as PersonalizationInstructionType,
                              }
                            : previous
                        )
                      }
                      className="rounded-[14px] border border-[rgba(255,255,255,0.08)] bg-[rgba(8,11,18,0.72)] px-3 py-3 text-sm text-white outline-none transition focus:border-[rgba(255,213,127,0.36)]"
                    >
                      <option value="response_style">Response Style</option>
                      <option value="user_profile">User Profile</option>
                    </select>
                  </label>

                  <label className="flex flex-col gap-2">
                    <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,213,127,0.68)]">
                      Title
                    </span>
                    <input
                      aria-label="Instruction title"
                      type="text"
                      value={composer.title}
                      onChange={(event) =>
                        setComposer((previous) =>
                          previous ? { ...previous, title: event.target.value } : previous
                        )
                      }
                      placeholder="예: 설명 방식"
                      className="rounded-[14px] border border-[rgba(255,255,255,0.08)] bg-[rgba(8,11,18,0.72)] px-3 py-3 text-sm text-white outline-none transition placeholder:text-[rgba(170,170,179,0.4)] focus:border-[rgba(255,213,127,0.36)]"
                    />
                  </label>
                </div>

                <label className="mt-4 flex flex-col gap-2">
                  <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[rgba(255,213,127,0.68)]">
                    Content
                  </span>
                  <textarea
                    aria-label="Instruction content"
                    value={composer.contentText}
                    onChange={(event) =>
                      setComposer((previous) =>
                        previous ? { ...previous, contentText: event.target.value } : previous
                      )
                    }
                    placeholder="예: 추상 개념은 예시와 함께 설명한다"
                    className="min-h-[120px] rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-[rgba(8,11,18,0.72)] px-3 py-3 text-sm text-white outline-none transition placeholder:text-[rgba(170,170,179,0.4)] focus:border-[rgba(255,213,127,0.36)]"
                  />
                </label>

                <label className="mt-4 inline-flex items-center gap-3 text-sm text-[rgba(231,231,240,0.88)]">
                  <input
                    aria-label="Instruction enabled"
                    type="checkbox"
                    checked={composer.enabled}
                    onChange={(event) =>
                      setComposer((previous) =>
                        previous ? { ...previous, enabled: event.target.checked } : previous
                      )
                    }
                    className="h-4 w-4 rounded border border-[rgba(255,255,255,0.12)] bg-transparent"
                  />
                  <span>Save this instruction as enabled</span>
                </label>

                {composerError ? (
                  <div className="mt-4 rounded-[14px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                    {composerError}
                  </div>
                ) : null}

                <div className="mt-5 flex flex-wrap justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setComposer(null);
                      setComposerError('');
                    }}
                    className="rounded-[14px] border border-[rgba(255,255,255,0.08)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.16em] text-[rgba(231,231,240,0.82)] transition hover:bg-[rgba(255,255,255,0.04)]"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => void submitComposer()}
                    disabled={submittingComposer}
                    className="inline-flex min-w-[150px] items-center justify-center gap-2 rounded-[14px] bg-[rgba(255,213,127,0.18)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.16em] text-[#ffd57f] transition hover:bg-[rgba(255,213,127,0.24)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {submittingComposer ? <Loader2 size={14} className="animate-spin" /> : null}
                    <span>{composer.mode === 'create' ? 'Create Instruction' : 'Save Changes'}</span>
                  </button>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {sortedInstructions.length === 0 ? (
          <section className="rounded-[24px] border border-dashed border-[rgba(255,255,255,0.1)] bg-[rgba(17,21,31,0.42)] px-6 py-10 text-center">
            <div className="mx-auto max-w-[34rem]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(255,213,127,0.72)]">
                Empty State
              </div>
              <h3 className="mt-3 text-[24px] font-semibold tracking-[-0.04em] text-white">
                No explicit instructions yet
              </h3>
              <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.76)]">
                Add bounded response defaults or profile notes that should help future replies without overriding the current turn.
              </p>
            </div>
          </section>
        ) : (
          <div className="space-y-4">
            {sortedInstructions.map((instruction) => (
              <PersonalizationInstructionCard
                key={instruction.id}
                instruction={instruction}
                deleting={deletingInstructionId === instruction.id}
                saving={savingInstructionId === instruction.id}
                onEdit={(item) => {
                  setComposer(createInstructionDraft(item));
                  setComposerError('');
                }}
                onDelete={handleDeleteInstruction}
                onToggle={handleInstructionToggle}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
