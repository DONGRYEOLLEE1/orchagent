"use client";

import React, { useEffect, useRef } from 'react';
import { Loader2, Paperclip } from 'lucide-react';

import RepositoryBindingPanel from '@/components/workspace/RepositoryBindingPanel';
import { SelectedAttachmentTray } from '@/components/workspace/internal/SelectedAttachmentTray';
import type {
  DraftAttachmentItem,
  DraftAttachmentStatusMap,
} from '@/components/workspace/internal/attachment-utils';
import type { RepositoryBinding } from '@/types/thread';

export interface ComposerPanelProps {
  /** Composer text value (controlled). */
  input: string;
  /** Setter for the composer text (mirrors `useState` shape so existing handlers can pass theirs directly). */
  onInputChange: (next: string) => void;
  /** Pending draft attachments (uploaded on submit). */
  selectedFiles: DraftAttachmentItem[];
  /** Per-file upload status keyed by `localKey`. */
  selectedFileStatuses: DraftAttachmentStatusMap;
  /** Aggregate upload UI state for the tray. */
  attachmentUploadState: 'idle' | 'uploading' | 'error';
  /** Composer-level attachment error string. */
  attachmentError: string;
  /** Add files button handler — fires when the user picks new files. */
  onAttachmentChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  /** Remove a single draft attachment by index in `selectedFiles`. */
  onRemoveAttachment: (index: number) => void;
  /** Submit handler bound to the composer form. */
  onSubmit: (event: React.FormEvent) => void | Promise<void>;
  /** Hard-disables the composer while a stream/HITL is in-flight. */
  isInteractionLocked: boolean;
  /** True iff a stream is currently loading (controls Send button spinner). */
  loading: boolean;
  /** True iff at least one draft attachment is in `ready`/`uploading` state (not all failed). */
  hasSendableAttachments: boolean;
  /** Bound repository for the active thread (rendered in the inline panel section). */
  repoBinding: RepositoryBinding | null | undefined;
  /** True while a repo bind / delete / materialize request is in flight. */
  repoBindingLoading: boolean;
  /** Latest repo-binding error message. */
  repoBindingError: string;
  /** Bind a repository by url (`github_url` or `git_url`). */
  onBindRepositoryUrl: (
    sourceType: 'github_url' | 'git_url',
    sourceRef: string
  ) => void | Promise<void>;
  /** Bind a repository from an uploaded zip archive. */
  onBindRepositoryZip: (file: File) => void | Promise<void>;
  /** Delete the active thread's repo binding. */
  onDeleteRepositoryBinding: () => void | Promise<void>;
  /** Materialize the bound repo into the runtime sandbox. */
  onMaterializeRepository: () => void | Promise<void>;
}

/**
 * Bottom composer slice of WorkspaceRouteRoot: textarea + attach trigger +
 * Send button + Attach repository toggle. State (input/attachments/repo)
 * stays in the parent; this component only renders + emits callbacks.
 */
export function ComposerPanel({
  input,
  onInputChange,
  selectedFiles,
  selectedFileStatuses,
  attachmentUploadState,
  attachmentError,
  onAttachmentChange,
  onRemoveAttachment,
  onSubmit,
  isInteractionLocked,
  loading,
  hasSendableAttachments,
  repoBinding,
  repoBindingLoading,
  repoBindingError,
  onBindRepositoryUrl,
  onBindRepositoryZip,
  onDeleteRepositoryBinding,
  onMaterializeRepository,
}: ComposerPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerFormRef = useRef<HTMLFormElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = composerTextareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  return (
    <div className="border-t border-[rgba(255,255,255,0.05)] bg-[rgba(29,31,40,0.8)] px-6 py-6 backdrop-blur-xl md:px-8">
      <form
        ref={composerFormRef}
        onSubmit={onSubmit}
        className="mx-auto flex w-full max-w-[720px] flex-col gap-3"
      >
        <SelectedAttachmentTray
          files={selectedFiles}
          statuses={selectedFileStatuses}
          uploadState={attachmentUploadState}
          error={attachmentError}
          onRemove={onRemoveAttachment}
        />

        <p className="px-1 text-right text-[9px] tracking-[0.18em] text-[rgba(170,170,179,0.45)]">
          ENTER · SEND &nbsp;·&nbsp; SHIFT + ENTER · NEW LINE
        </p>
        <div className="flex items-stretch gap-2">
          <div className="flex flex-1 items-center rounded-[16px] border border-[rgba(255,255,255,0.1)] bg-black px-2 transition focus-within:border-[rgba(143,245,255,0.35)]">
            <button
              type="button"
              aria-label="Add files"
              onClick={() => fileInputRef.current?.click()}
              disabled={isInteractionLocked}
              className="shrink-0 p-2 text-[rgba(170,170,179,0.72)] transition hover:text-[#8ff5ff] disabled:text-slate-800"
            >
              <Paperclip size={18} />
            </button>
            <input
              type="file"
              multiple
              accept="image/*,.pdf,.xlsx,.csv,.json,.docx"
              className="hidden"
              ref={fileInputRef}
              onChange={onAttachmentChange}
            />
            <textarea
              ref={composerTextareaRef}
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  !isInteractionLocked
                ) {
                  e.preventDefault();
                  composerFormRef.current?.requestSubmit();
                }
              }}
              placeholder="Message OrchAgent..."
              rows={1}
              className="flex-1 resize-none border-0 bg-transparent py-2 leading-6 text-[#e7e7f0] outline-none placeholder:text-[rgba(170,170,179,0.42)]"
              style={{ fontSize: '14px', maxHeight: '200px', overflowY: 'auto' }}
              disabled={isInteractionLocked}
            />
          </div>
          <button
            type="submit"
            aria-label="Send message"
            disabled={isInteractionLocked || (!input.trim() && !hasSendableAttachments)}
            className="shrink-0 self-stretch inline-flex items-center justify-center rounded-[12px] bg-[#8ff5ff] px-5 text-[12px] font-bold uppercase tracking-[0.18em] text-[#005d63] shadow-[0px_10px_15px_-3px_rgba(143,245,255,0.2),0px_4px_6px_-4px_rgba(143,245,255,0.2)] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-600"
          >
            {loading ? <Loader2 className="animate-spin" size={16} /> : 'Send'}
          </button>
        </div>

        {repoBinding || repoBindingError ? (
          // On xl+ the bound repo context lives in the right aside (Coding tab).
          // Keep it centrally visible on narrower viewports where the aside is hidden.
          <div className="xl:hidden">
            <RepositoryBindingPanel
              binding={repoBinding ?? null}
              disabled={isInteractionLocked}
              loading={repoBindingLoading}
              error={repoBindingError}
              onBindUrl={onBindRepositoryUrl}
              onBindZip={onBindRepositoryZip}
              onDeleteBinding={onDeleteRepositoryBinding}
              onMaterialize={onMaterializeRepository}
            />
          </div>
        ) : (
          <details className="group rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(29,31,40,0.55)] px-4 py-2 text-[12px] text-[rgba(170,170,179,0.9)]">
            <summary className="cursor-pointer select-none list-none text-[10px] font-semibold uppercase tracking-[0.22em] text-[rgba(143,245,255,0.78)] outline-none">
              + Attach repository (coding mode)
            </summary>
            <div className="mt-3">
              <RepositoryBindingPanel
                binding={repoBinding ?? null}
                disabled={isInteractionLocked}
                loading={repoBindingLoading}
                error={repoBindingError}
                onBindUrl={onBindRepositoryUrl}
                onBindZip={onBindRepositoryZip}
                onDeleteBinding={onDeleteRepositoryBinding}
                onMaterialize={onMaterializeRepository}
              />
            </div>
          </details>
        )}
      </form>
    </div>
  );
}

export default ComposerPanel;
