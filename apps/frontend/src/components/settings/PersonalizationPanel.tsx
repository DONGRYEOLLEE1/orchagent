"use client";

import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Loader2, Save, Sparkles, UserCircle2 } from 'lucide-react';

import {
  createPersonalizationInstruction,
  deletePersonalizationInstruction,
  fetchPersonalizationInstructions,
  fetchPersonalizationSettings,
  patchPersonalizationSettings,
  updatePersonalizationInstruction,
} from '@/lib/api';
import type { PersonalizationInstruction } from '@/types/memory';

function collapseText(value: string) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .join('\n');
}

function collectTypeContent(
  instructions: PersonalizationInstruction[],
  instructionType: PersonalizationInstruction['instruction_type']
) {
  return instructions
    .filter((instruction) => instruction.instruction_type === instructionType)
    .map((instruction) => instruction.content_text.trim())
    .filter(Boolean)
    .join('\n');
}

async function syncInstructionType(params: {
  instructionType: PersonalizationInstruction['instruction_type'];
  title: string;
  nextContent: string;
  existing: PersonalizationInstruction[];
}) {
  const { instructionType, title, nextContent, existing } = params;
  const normalizedContent = collapseText(nextContent);
  const [primary, ...rest] = existing;

  if (!normalizedContent) {
    await Promise.all(existing.map((instruction) => deletePersonalizationInstruction(instruction.id)));
    return;
  }

  if (primary) {
    await updatePersonalizationInstruction({
      instructionId: primary.id,
      instructionType,
      title,
      contentText: normalizedContent,
      enabled: true,
    });
  } else {
    await createPersonalizationInstruction({
      instructionType,
      title,
      contentText: normalizedContent,
      enabled: true,
    });
  }

  if (rest.length > 0) {
    await Promise.all(rest.map((instruction) => deletePersonalizationInstruction(instruction.id)));
  }
}

function SectionField({
  icon,
  label,
  helper,
  placeholder,
  value,
  onChange,
}: {
  icon: ReactNode;
  label: string;
  helper: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <section className="space-y-6">
      <div className="flex items-start gap-4">
        <span className="inline-flex rounded-[14px] bg-[rgba(122,101,255,0.08)] p-2 text-[rgba(171,160,255,0.88)]">
          {icon}
        </span>
        <div>
          <h2 className="text-[22px] font-semibold tracking-[-0.03em] text-white">{label}</h2>
          <p className="mt-1 text-[13px] leading-6 text-[rgba(170,170,179,0.72)]">{helper}</p>
        </div>
      </div>

      <div className="rounded-[22px] border border-[rgba(255,255,255,0.06)] bg-[rgba(20,24,34,0.72)] p-[1px]">
        <textarea
          aria-label={label}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="min-h-[96px] w-full resize-none rounded-[21px] border-0 bg-[rgba(14,17,26,0.92)] px-6 py-6 text-[14px] leading-7 text-[rgba(231,231,240,0.9)] outline-none placeholder:text-[rgba(170,170,179,0.3)]"
        />
      </div>
    </section>
  );
}

export function PersonalizationPanel() {
  const [instructions, setInstructions] = useState<PersonalizationInstruction[]>([]);
  const [aboutYou, setAboutYou] = useState('');
  const [responseStyle, setResponseStyle] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [settings, loadedInstructions] = await Promise.all([
        fetchPersonalizationSettings(),
        fetchPersonalizationInstructions(),
      ]);

      setInstructions(loadedInstructions);
      setAboutYou(collectTypeContent(loadedInstructions, 'user_profile'));
      setResponseStyle(collectTypeContent(loadedInstructions, 'response_style'));

      if (!settings.instructions_enabled) {
        setSuccess('Saved personalization exists, but runtime application is currently paused.');
      } else {
        setSuccess('');
      }
    } catch (personalizationError) {
      setError(personalizationError instanceof Error ? personalizationError.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const grouped = useMemo(
    () => ({
      userProfile: instructions.filter((instruction) => instruction.instruction_type === 'user_profile'),
      responseStyle: instructions.filter((instruction) => instruction.instruction_type === 'response_style'),
    }),
    [instructions]
  );

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await Promise.all([
        syncInstructionType({
          instructionType: 'user_profile',
          title: 'About You',
          nextContent: aboutYou,
          existing: grouped.userProfile,
        }),
        syncInstructionType({
          instructionType: 'response_style',
          title: 'Response Style',
          nextContent: responseStyle,
          existing: grouped.responseStyle,
        }),
      ]);

      await patchPersonalizationSettings({ instructionsEnabled: true });
      await load();
      setSuccess('Personalization settings saved.');
    } catch (personalizationError) {
      setError(personalizationError instanceof Error ? personalizationError.message : 'Unknown error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[20rem] items-center justify-center rounded-[28px] border border-[rgba(255,255,255,0.06)] bg-[rgba(11,14,22,0.78)]">
        <div className="flex items-center gap-3 text-[14px] text-[rgba(170,170,179,0.78)]">
          <Loader2 size={18} className="animate-spin text-[#8ff5ff]" />
          <span>Loading personalization...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-12">
      <SectionField
        icon={<UserCircle2 size={18} />}
        label="About You"
        helper="What would you like the AI agent to know about you to provide better responses?"
        placeholder="Example: I am a senior software architect focused on scalable cloud infrastructure. I prefer technical depth and architectural patterns over basic syntax..."
        value={aboutYou}
        onChange={setAboutYou}
      />

      <SectionField
        icon={<Sparkles size={18} />}
        label="Response Style"
        helper="How would you like the AI agent to respond?"
        placeholder="Example: Be concise and direct. Use bullet points for complex explanations. Avoid corporate jargon and maintain an analytical yet helpful tone..."
        value={responseStyle}
        onChange={setResponseStyle}
      />

      {error ? (
        <div className="rounded-[18px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {success ? (
        <div className="rounded-[18px] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {success}
        </div>
      ) : null}

      <div className="flex justify-end border-t border-[rgba(255,255,255,0.06)] pt-8">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
          className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-6 py-3 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          <span>Save Personalization</span>
        </button>
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <div className="h-1 rounded-full bg-gradient-to-r from-[#8ff5ff] to-transparent" />
        <div className="h-1 rounded-full bg-gradient-to-r from-[#8364ff] to-transparent" />
        <div className="h-1 rounded-full bg-gradient-to-r from-[#61d6ff] to-transparent" />
      </div>
    </div>
  );
}
