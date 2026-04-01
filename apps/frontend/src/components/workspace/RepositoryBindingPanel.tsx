import { GitBranch, Loader2, Paperclip, RefreshCw, Unplug } from 'lucide-react';
import { useRef, useState } from 'react';

import type { RepositoryBinding } from '@/types/thread';

export default function RepositoryBindingPanel({
  binding,
  disabled,
  loading,
  error,
  onBindUrl,
  onBindZip,
  onDeleteBinding,
  onMaterialize,
}: {
  binding: RepositoryBinding | null;
  disabled: boolean;
  loading: boolean;
  error: string;
  onBindUrl: (sourceType: 'github_url' | 'git_url', sourceRef: string) => Promise<void> | void;
  onBindZip: (file: File) => Promise<void> | void;
  onDeleteBinding: () => Promise<void> | void;
  onMaterialize: () => Promise<void> | void;
}) {
  const [sourceInput, setSourceInput] = useState('');
  const zipInputRef = useRef<HTMLInputElement>(null);

  const submitUrl = async (sourceType: 'github_url' | 'git_url') => {
    const value = sourceInput.trim();
    if (!value) {
      return;
    }
    await onBindUrl(sourceType, value);
    setSourceInput('');
  };

  return (
    <div className="rounded-[18px] border border-[rgba(255,255,255,0.08)] bg-[rgba(17,19,26,0.72)] px-4 py-4 shadow-lg shadow-black/20">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(143,245,255,0.78)]">
            <GitBranch size={14} />
            Repository Context
          </div>
          <p className="mt-2 text-[13px] leading-6 text-[rgba(170,170,179,0.82)]">
            Bind a Git URL or zip archive before asking for code changes.
          </p>
        </div>
        {loading ? <Loader2 size={16} className="animate-spin text-[#8ff5ff]" /> : null}
      </div>

      {binding ? (
        <div className="mt-4 rounded-[16px] border border-[rgba(143,245,255,0.12)] bg-[rgba(35,38,46,0.28)] px-4 py-4">
          <div className="text-[13px] font-semibold text-[#e7e7f0]">{binding.display_name}</div>
          <div className="mt-1 break-all text-[12px] text-[rgba(170,170,179,0.78)]">
            {binding.source_label}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void onMaterialize()}
              disabled={disabled || loading}
              className="inline-flex items-center gap-2 rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(231,231,240,0.88)] transition hover:border-[rgba(143,245,255,0.28)] disabled:opacity-50"
            >
              <RefreshCw size={14} />
              Refresh Repo
            </button>
            <button
              type="button"
              onClick={() => void onDeleteBinding()}
              disabled={disabled || loading}
              className="inline-flex items-center gap-2 rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.02)] px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(255,209,209,0.92)] transition hover:border-[rgba(255,93,93,0.3)] disabled:opacity-50"
            >
              <Unplug size={14} />
              Unbind Repo
            </button>
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-col gap-3">
        <input
          value={sourceInput}
          onChange={(e) => setSourceInput(e.target.value)}
          placeholder="Paste GitHub URL or git URL"
          disabled={disabled || loading}
          className="w-full rounded-[14px] border border-[rgba(255,255,255,0.08)] bg-black px-4 py-3 text-[13px] text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.3)] disabled:opacity-50"
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void submitUrl('github_url')}
            disabled={disabled || loading || !sourceInput.trim()}
            className="rounded-[12px] bg-[#8ff5ff] px-4 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-[#005d63] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-600"
          >
            Bind GitHub URL
          </button>
          <button
            type="button"
            onClick={() => void submitUrl('git_url')}
            disabled={disabled || loading || !sourceInput.trim()}
            className="rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-4 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.28)] disabled:opacity-50"
          >
            Bind Git URL
          </button>
          <button
            type="button"
            onClick={() => zipInputRef.current?.click()}
            disabled={disabled || loading}
            className="inline-flex items-center gap-2 rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] px-4 py-2 text-[11px] font-bold uppercase tracking-[0.16em] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.28)] disabled:opacity-50"
          >
            <Paperclip size={14} />
            Bind Repo Zip
          </button>
          <input
            ref={zipInputRef}
            type="file"
            accept=".zip,application/zip"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                void onBindZip(file);
              }
              e.currentTarget.value = '';
            }}
          />
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded-[12px] border border-red-500/20 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">
          {error}
        </div>
      ) : null}
    </div>
  );
}
