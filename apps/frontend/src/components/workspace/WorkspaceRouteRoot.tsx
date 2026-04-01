"use client";

import React, { useState, useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  Send,
  Loader2,
  Bot,
  Image as ImageIcon,
  Paperclip,
  FileText,
  FileSpreadsheet,
  FileJson,
  X,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import NextImage from 'next/image';
import { ChatAttachment, ChatMessage, StreamEvent, ToolExecution } from '@/types/agent';
import type { AuthUser } from '@/types/auth';
import type { ActionSpaceState, ActiveThreadState, StreamSessionState, ThreadCollectionState } from '@/types/thread';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  bindRepository,
  bindRepositoryZip,
  changePasswordUser,
  deleteRepositoryBinding,
  deleteThread,
  fetchThreadDetail,
  fetchThreadTelemetry,
  fetchThreads,
  generateAiThreadTitle,
  generateSuggestedQueries,
  materializeRepository,
  patchThread,
  resumeChatStream,
  sendChatStream,
  type UploadBatchError,
  uploadChatAttachments,
} from '@/lib/api';
import { appendAssistantText, parseSseBlock, pushUniqueHistory, splitSseBlocks } from '@/lib/chat-stream';
import { preprocessMarkdown } from '@/lib/markdown';
import {
  applyThreadSummaryToActiveThread,
  createActiveThreadStateFromDetail,
  createInitialActionSpaceState,
  createInitialActiveThreadState,
  createHistoricalStreamSessionState,
  createOptimisticThreadSummary,
  patchThreadSummary,
  createInitialStreamSessionState,
  createInitialThreadCollectionState,
  sortThreadSummaries,
  upsertThreadSummary,
} from '@/lib/workspace-state';
import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';
import { HITLPanel } from '@/components/HITLPanel';
import { AgentTimeline } from '@/components/sidebar/AgentTimeline';
import { ThreadListSidebar } from '@/components/sidebar/ThreadListSidebar';
import { LiveToolStatusStrip } from '@/components/workspace/LiveToolStatusStrip';
import { ReasoningSummaryPanel } from '@/components/workspace/ReasoningSummaryPanel';
import { SuggestedQueriesPanel } from '@/components/workspace/SuggestedQueriesPanel';
import { AccountDrawer } from '@/components/workspace/AccountDrawer';
import RepositoryBindingPanel from '@/components/workspace/RepositoryBindingPanel';
import { WorkspaceTopNav } from '@/components/workspace/WorkspaceTopNav';

function appendReasoningEntry(
  entries: ActionSpaceState['reasoningEntries'],
  payload: {
    node?: string | null;
    display_name?: string | null;
    content: string;
    timestamp: string;
    run_id?: string;
  }
): ActionSpaceState['reasoningEntries'] {
  const nextEntries = [...entries];
  const mergeTargetId = payload.run_id || `${payload.node || 'reasoning'}:${payload.timestamp}`;
  const lastEntry = nextEntries[nextEntries.length - 1];

  if (lastEntry && payload.run_id && lastEntry.runId === payload.run_id) {
    nextEntries[nextEntries.length - 1] = {
      ...lastEntry,
      content: lastEntry.content + payload.content,
      timestamp: payload.timestamp || lastEntry.timestamp,
    };
    return nextEntries;
  }

  nextEntries.push({
    id: mergeTargetId,
    node: payload.node,
    displayName: payload.display_name,
    content: payload.content,
    timestamp: payload.timestamp,
    runId: payload.run_id,
  });
  return nextEntries;
}

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function deriveRouteThreadId(pathname: string): string | null {
  const match = pathname.match(/^\/c\/([^/?#]+)/);
  if (!match) {
    return null;
  }

  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function buildThreadPath(threadId: string): string {
  return `/c/${encodeURIComponent(threadId)}`;
}
// --- Markdown Renderer ---
const MarkdownContent = ({ content }: { content: string }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        code({ inline, className, children, ...props }: { inline?: boolean; className?: string; children?: React.ReactNode }) {
          const match = /language-(\w+)/.exec(className || '');
          return !inline && match ? (
            <SyntaxHighlighter
              style={atomDark}
              language={match[1]}
              PreTag="div"
              className="rounded-lg !my-4 !bg-black/40 border border-white/5"
              {...props}
            >
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          ) : (
            <code className={cn("bg-black/40 px-1.5 py-0.5 rounded text-blue-300 font-mono text-[0.9em]", className)} {...props}>
              {children}
            </code>
          );
        },
        table: ({ children }) => (
          <div className="overflow-x-auto my-4 rounded-lg border border-slate-800">
            <table className="w-full text-left text-xs border-collapse bg-slate-900/50">
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => <th className="p-2 border-b border-slate-800 bg-slate-800/50 font-bold">{children}</th>,
        td: ({ children }) => <td className="p-2 border-b border-slate-800">{children}</td>,
        p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-6 mb-4 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-6 mb-4 space-y-1">{children}</ol>,
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="cursor-pointer break-all text-[#8ff5ff] underline decoration-[rgba(143,245,255,0.4)] underline-offset-3 transition hover:text-[#c7fbff] hover:decoration-[rgba(199,251,255,0.9)]"
          >
            {children}
          </a>
        ),
      }}
    >
      {preprocessMarkdown(content)}
    </ReactMarkdown>
  );
};

// --- Helper Functions ---
const SUPPORTED_ATTACHMENT_LABEL = '이미지, PDF, XLSX, CSV, JSON, DOCX만 지원합니다.';
const ATTACHMENT_MAX_FILES = 5;
const ATTACHMENT_MAX_TOTAL_BYTES = 30 * 1024 * 1024;
const ATTACHMENT_MAX_BYTES_BY_KIND: Record<Exclude<ChatAttachment['kind'], 'artifact'>, number> = {
  image: 10 * 1024 * 1024,
  pdf: 20 * 1024 * 1024,
  spreadsheet: 20 * 1024 * 1024,
  csv: 10 * 1024 * 1024,
  json: 20 * 1024 * 1024,
  docx: 20 * 1024 * 1024,
};

type DraftAttachmentStatus = 'ready' | 'uploading' | 'failed';

type DraftAttachmentItem = {
  file: File;
  localKey: string;
};

type DraftAttachmentStatusMap = Record<
  string,
  {
    status: DraftAttachmentStatus;
    error?: string;
  }
>;

function inferDraftAttachmentKind(file: File): ChatAttachment['kind'] | null {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (file.type.startsWith('image/')) return 'image';
  if (file.type === 'application/pdf' || extension === 'pdf') return 'pdf';
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    extension === 'xlsx'
  ) {
    return 'spreadsheet';
  }
  if (file.type === 'text/csv' || extension === 'csv') return 'csv';
  if (file.type === 'application/json' || extension === 'json') return 'json';
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    extension === 'docx'
  ) {
    return 'docx';
  }
  return null;
}

function draftAttachmentKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatAttachmentBytes(sizeBytes?: number | null): string {
  if (!sizeBytes || sizeBytes <= 0) return '';
  if (sizeBytes < 1024) return `${sizeBytes}B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)}KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)}MB`;
}

function maxBytesForDraftKind(kind: Exclude<ChatAttachment['kind'], 'artifact'>): number {
  return ATTACHMENT_MAX_BYTES_BY_KIND[kind];
}

function summarizeUploadErrors(errors: UploadBatchError[]): string {
  return errors.map((error) => `${error.file_name}: ${error.detail}`).join('\n');
}

function validateIncomingDraftFiles(params: {
  existingFiles: DraftAttachmentItem[];
  existingStatuses: DraftAttachmentStatusMap;
  incomingFiles: File[];
}): {
  accepted: DraftAttachmentItem[];
  nextStatusPatch: DraftAttachmentStatusMap;
  message: string;
} {
  const { existingFiles, existingStatuses, incomingFiles } = params;
  const accepted: DraftAttachmentItem[] = [];
  const nextStatusPatch: DraftAttachmentStatusMap = {};
  const errors: string[] = [];

  const existingReadyFiles = existingFiles.filter(
    (item) => existingStatuses[item.localKey]?.status !== 'failed'
  );
  let acceptedCount = existingReadyFiles.length;
  let acceptedBytes = existingReadyFiles.reduce((sum, item) => sum + item.file.size, 0);

  for (const file of incomingFiles) {
    const kind = inferDraftAttachmentKind(file);
    if (!kind || kind === 'artifact') {
      errors.push(`${file.name}: ${SUPPORTED_ATTACHMENT_LABEL}`);
      continue;
    }

    if (acceptedCount >= ATTACHMENT_MAX_FILES) {
      errors.push(`${file.name}: 한 번에 최대 ${ATTACHMENT_MAX_FILES}개 파일만 첨부할 수 있습니다.`);
      continue;
    }

    const maxBytes = maxBytesForDraftKind(kind);
    if (file.size > maxBytes) {
      errors.push(
        `${file.name}: ${kind.toUpperCase()} 파일은 ${formatAttachmentBytes(maxBytes)}까지 첨부할 수 있습니다.`
      );
      continue;
    }

    if (acceptedBytes + file.size > ATTACHMENT_MAX_TOTAL_BYTES) {
      errors.push(
        `${file.name}: 첨부 파일 총합은 ${formatAttachmentBytes(ATTACHMENT_MAX_TOTAL_BYTES)}를 넘을 수 없습니다.`
      );
      continue;
    }

    const localKey = draftAttachmentKey(file);
    accepted.push({ file, localKey });
    nextStatusPatch[localKey] = { status: 'ready' };
    acceptedCount += 1;
    acceptedBytes += file.size;
  }

  return {
    accepted,
    nextStatusPatch,
    message: errors.join('\n'),
  };
}

function attachmentIcon(attachment: ChatAttachment) {
  switch (attachment.kind) {
    case 'spreadsheet':
    case 'csv':
      return <FileSpreadsheet size={15} />;
    case 'json':
      return <FileJson size={15} />;
    case 'image':
      return <ImageIcon size={15} />;
    default:
      return <FileText size={15} />;
  }
}

const buildOptimisticAttachments = (files: File[]): ChatAttachment[] =>
  files.map((file, index) => {
    const kind = inferDraftAttachmentKind(file) || 'artifact';
    return {
      kind,
      url: kind === 'image' ? URL.createObjectURL(file) : undefined,
      alt: file.name || `첨부 파일 ${index + 1}`,
      file_name: file.name,
      mime_type: file.type || null,
      size_bytes: file.size,
    };
  });

const MessageAttachmentStrip = ({
  attachments,
  align = 'end',
  onImageSelect,
}: {
  attachments: ChatAttachment[];
  align?: 'start' | 'end';
  onImageSelect?: (attachment: ChatAttachment) => void;
}) => {
  const imageAttachments = attachments.filter(
    (attachment) =>
      attachment.kind === 'image' || Boolean(attachment.mime_type?.startsWith('image/'))
  );
  const fileAttachments = attachments.filter(
    (attachment) =>
      attachment.kind !== 'image' && !attachment.mime_type?.startsWith('image/')
  );
  if (imageAttachments.length === 0 && fileAttachments.length === 0) {
    return null;
  }

  const visibleAttachments = imageAttachments.slice(0, 4);
  const hiddenCount = imageAttachments.length - visibleAttachments.length;
  const isSingle = visibleAttachments.length === 1;

  return (
    <div className={cn('mb-3 w-[244px] space-y-2', align === 'end' ? 'self-end' : 'self-start')}>
      {visibleAttachments.length > 0 ? (
        <div className={cn('grid gap-2', isSingle ? 'grid-cols-1' : 'grid-cols-2')}>
          {visibleAttachments.map((attachment, index) => (
            <button
              type="button"
              key={`${attachment.url || attachment.alt}_${index}`}
              onClick={() => onImageSelect?.(attachment)}
              className={cn(
                'relative overflow-hidden rounded-[22px] border border-[rgba(255,255,255,0.1)] bg-[rgba(35,38,46,0.46)] shadow-[0px_18px_32px_-24px_rgba(0,0,0,0.9)] transition hover:brightness-110 cursor-zoom-in',
                isSingle ? 'aspect-[4/3]' : 'aspect-square'
              )}
              aria-label={`${attachment.alt} 크게 보기`}
            >
              {attachment.url ? (
                <NextImage
                  src={attachment.url}
                  alt={attachment.alt}
                  fill
                  sizes={isSingle ? '244px' : '118px'}
                  className="object-cover"
                  unoptimized
                />
              ) : null}
              {hiddenCount > 0 && index === visibleAttachments.length - 1 ? (
                <div className="absolute inset-0 flex items-center justify-center bg-[rgba(7,9,13,0.64)] text-[18px] font-semibold text-white">
                  +{hiddenCount}
                </div>
              ) : null}
            </button>
          ))}
        </div>
      ) : null}

      {fileAttachments.map((attachment, index) => (
        <div
          key={`${attachment.file_name || attachment.alt}_${index}`}
          className="flex items-center gap-3 rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-[rgba(35,38,46,0.52)] px-3 py-3 text-[#e7e7f0]"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(143,245,255,0.12)] text-[#8ff5ff]">
            {attachmentIcon(attachment)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] font-semibold leading-5">
              {attachment.file_name || attachment.alt}
            </div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
              {attachment.kind}
              {attachment.size_bytes ? ` · ${formatAttachmentBytes(attachment.size_bytes)}` : ''}
            </div>
          </div>
          {attachment.url ? (
            <a
              href={attachment.url}
              target="_blank"
              rel="noreferrer"
              className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8ff5ff] transition hover:text-[#c7fbff]"
            >
              Open
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
};

const ImageLightbox = ({
  attachment,
  onClose,
}: {
  attachment: ChatAttachment | null;
  onClose: () => void;
}) => {
  useEffect(() => {
    if (!attachment) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [attachment, onClose]);

  if (!attachment?.url) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[rgba(7,9,13,0.84)] px-6 py-6 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-label={`${attachment.alt} 확대 보기`}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-full w-full max-w-[1200px] items-center justify-center"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close image preview"
          className="absolute right-0 top-0 z-10 inline-flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] bg-[rgba(12,14,20,0.76)] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.32)] hover:text-[#8ff5ff]"
        >
          <X size={18} />
        </button>
        <div className="relative max-h-[88vh] w-full overflow-hidden rounded-[24px] border border-[rgba(255,255,255,0.08)] bg-[rgba(12,14,20,0.94)] p-4 shadow-[0px_30px_80px_rgba(0,0,0,0.55)]">
          <div className="mb-3 pr-14 text-[12px] font-semibold uppercase tracking-[0.18em] text-[rgba(170,170,179,0.74)]">
            {attachment.file_name || attachment.alt}
          </div>
          <div className="relative flex max-h-[78vh] min-h-[320px] items-center justify-center overflow-hidden rounded-[18px] bg-black/40">
            <NextImage
              src={attachment.url}
              alt={attachment.alt}
              width={1400}
              height={1000}
              className="max-h-[78vh] w-auto max-w-full object-contain"
              unoptimized
            />
          </div>
        </div>
      </div>
    </div>
  );
};

const SelectedAttachmentTray = ({
  files,
  statuses,
  uploadState,
  error,
  onRemove,
}: {
  files: DraftAttachmentItem[];
  statuses: DraftAttachmentStatusMap;
  uploadState: 'idle' | 'uploading' | 'error';
  error: string;
  onRemove: (index: number) => void;
}) => {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.4)] p-3">
      {files.map((item, i) => {
        const { file, localKey } = item;
        const kind = inferDraftAttachmentKind(file);
        const isImage = kind === 'image';
        const state = statuses[localKey]?.status || 'ready';
        const stateError = statuses[localKey]?.error;
        const stateLabel =
          state === 'uploading' ? 'UPLOADING' : state === 'failed' ? 'FAILED' : 'READY';
        const stateClassName =
          state === 'uploading'
            ? 'text-[#8ff5ff]'
            : state === 'failed'
              ? 'text-red-300'
              : 'text-emerald-300';

        return (
          <div
            key={`${localKey}_${i}`}
            className={cn(
              'relative overflow-hidden rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(7,9,13,0.72)]',
              isImage ? 'h-16 w-16' : 'flex min-w-[168px] max-w-[240px] items-center gap-3 px-3 py-3'
            )}
          >
            {isImage ? (
              <NextImage
                src={URL.createObjectURL(file)}
                alt={file.name}
                width={64}
                height={64}
                className="h-full w-full object-cover"
                unoptimized
              />
            ) : (
              <>
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(143,245,255,0.12)] text-[#8ff5ff]">
                  {attachmentIcon({
                    kind: kind || 'artifact',
                    alt: file.name,
                    file_name: file.name,
                    size_bytes: file.size,
                  })}
                </div>
                <div className="min-w-0 flex-1 pr-6">
                  <div className="truncate text-[12px] font-semibold text-[#e7e7f0]">
                    {file.name}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
                    {(kind || 'file').toUpperCase()} · {formatAttachmentBytes(file.size)}
                  </div>
                  <div className={cn('mt-1 text-[10px] font-bold uppercase tracking-[0.18em]', stateClassName)}>
                    {stateLabel}
                  </div>
                  {stateError ? (
                    <div className="mt-1 text-[11px] leading-4 text-red-300">{stateError}</div>
                  ) : null}
                </div>
              </>
            )}
            <button
              type="button"
              onClick={() => onRemove(i)}
              className="absolute right-1 top-1 rounded-full bg-[rgba(7,9,13,0.84)] p-1 text-white transition hover:bg-red-500"
            >
              <X size={10} />
            </button>
          </div>
        );
      })}
      <div className="w-full pt-1 text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
        {uploadState === 'uploading' ? 'Uploading files...' : 'Files ready to send'}
      </div>
      {error ? <div className="w-full text-[12px] text-red-300">{error}</div> : null}
    </div>
  );
};

// --- Components ---

const AuthLoadingScreen = ({ message }: { message: string }) => (
  <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 px-8 py-7 shadow-2xl shadow-black/40 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <Loader2 size={18} className="animate-spin text-blue-400" />
        <span className="text-sm text-slate-300">{message}</span>
      </div>
    </div>
  </main>
);

function MustChangePasswordView({
  currentUser,
  onPasswordChanged,
  onLogout,
}: {
  currentUser: AuthUser;
  onPasswordChanged: () => Promise<unknown>;
  onLogout: () => Promise<void> | void;
}) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await changePasswordUser({ currentPassword, newPassword });
      await onPasswordChanged();
    } catch (passwordError) {
      setError(passwordError instanceof Error ? passwordError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthScaffold
      title="Change Your Password"
      subtitle={`The bootstrap admin account is active as ${currentUser.login_id}. Replace the temporary password before using the workspace.`}
      footer={(
        <button
          type="button"
          onClick={() => void onLogout()}
          className="font-semibold text-[#8ff5ff] transition hover:text-[#c7fbff]"
        >
          Log Out
        </button>
      )}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="current-password">
              Current Password
            </label>
            <input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Enter the current password"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="new-password">
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Create a new password"
              disabled={submitting}
            />
            <p className="mt-2 text-xs italic leading-5 text-[rgba(170,170,179,0.68)]">
              Password must be at least 4 characters and include lowercase letters and numbers.
            </p>
          </div>

          {error ? (
            <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !currentPassword || !newPassword}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-4 py-4 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            <span>Change Password</span>
          </button>
      </form>
    </AuthScaffold>
  );
}

// --- Main Page ---

function WorkspaceApp({
  currentUser,
  onLogout,
  onUserUpdated,
  routeThreadId,
}: {
  currentUser: AuthUser;
  onLogout: () => Promise<void> | void;
  onUserUpdated: (user: AuthUser) => void;
  routeThreadId: string | null;
}) {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<DraftAttachmentItem[]>([]);
  const [selectedFileStatuses, setSelectedFileStatuses] = useState<DraftAttachmentStatusMap>({});
  const [attachmentUploadState, setAttachmentUploadState] = useState<'idle' | 'uploading' | 'error'>('idle');
  const [attachmentError, setAttachmentError] = useState('');
  const [repoBindingLoading, setRepoBindingLoading] = useState(false);
  const [repoBindingError, setRepoBindingError] = useState('');
  const [lightboxAttachment, setLightboxAttachment] = useState<ChatAttachment | null>(null);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [accountPanelOpen, setAccountPanelOpen] = useState(false);
  const [threadCollectionState, setThreadCollectionState] = useState<ThreadCollectionState>(() => createInitialThreadCollectionState());
  const [activeThreadState, setActiveThreadState] = useState<ActiveThreadState>(() => createInitialActiveThreadState());
  const [streamSessionState, setStreamSessionState] = useState<StreamSessionState>(() => createInitialStreamSessionState());
  const [actionSpaceState, setActionSpaceState] = useState<ActionSpaceState>(() => createInitialActionSpaceState());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toolIdCounterRef = useRef(0);
  const pendingTitleRequestIdsRef = useRef<Record<string, string>>({});
  const pendingTelemetryRequestIdsRef = useRef<Record<string, string>>({});
  const pendingSuggestionRequestIdsRef = useRef<Record<string, string>>({});
  const activeThreadIdRef = useRef('');

  const scrollRef = useRef<HTMLDivElement>(null);
  const actionSpaceRef = useRef<HTMLDivElement>(null);
  const isInteractionLocked =
    streamSessionState.loading ||
    streamSessionState.isInterrupted;
  const isHistoricalView = activeThreadState.viewMode === 'historical';

  useEffect(() => {
    activeThreadIdRef.current = activeThreadState.threadId;
  }, [activeThreadState.threadId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeThreadState.messages, streamSessionState.currentNode, actionSpaceState.reasoning]);

  useEffect(() => {
    if (actionSpaceRef.current) {
      actionSpaceRef.current.scrollTop = actionSpaceRef.current.scrollHeight;
    }
  }, [actionSpaceState.toolExecutions, actionSpaceState.reasoning]);

  useEffect(() => {
    let cancelled = false;

    const loadThreads = async () => {
      setThreadCollectionState(prev => ({
        ...prev,
        loadState: 'loading',
        error: '',
      }));

      try {
        const threads = await fetchThreads();
        if (cancelled) {
          return;
        }

        setThreadCollectionState({
          threads,
          loadState: 'success',
          error: '',
        });
      } catch (error) {
        if (cancelled) {
          return;
        }

        setThreadCollectionState(prev => ({
          ...prev,
          loadState: 'error',
          error: error instanceof Error ? error.message : 'Unknown error',
        }));
      }
    };

    void loadThreads();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isInteractionLocked) {
      return;
    }

    if (!activeThreadState.threadId) {
      return;
    }

    if (routeThreadId === activeThreadState.threadId) {
      return;
    }

    router.replace(buildThreadPath(activeThreadState.threadId));
  }, [activeThreadState.threadId, isInteractionLocked, routeThreadId, router]);

  // Route hydration must not depend on intermediate loading state updates,
  // or the in-flight detail fetch gets cancelled by its own optimistic reset.
  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(() => {
    if (streamSessionState.loading || streamSessionState.isInterrupted) {
      return;
    }

    if (!routeThreadId) {
      if (
        !activeThreadState.threadId &&
        activeThreadState.viewMode === 'draft' &&
        activeThreadState.messages.length === 0 &&
        activeThreadState.detailLoadState !== 'error'
      ) {
        return;
      }

      activeThreadIdRef.current = '';
      pendingTelemetryRequestIdsRef.current = {};
      pendingSuggestionRequestIdsRef.current = {};
      setInput('');
      setSelectedFiles([]);
      setSelectedFileStatuses({});
      setAttachmentUploadState('idle');
      setAttachmentError('');
      setRepoBindingLoading(false);
      setRepoBindingError('');
      setActiveThreadState(createInitialActiveThreadState());
      setStreamSessionState(createInitialStreamSessionState());
      setActionSpaceState(createInitialActionSpaceState());
      setMobileSidebarOpen(false);
      setAccountPanelOpen(false);
      return;
    }

    if (routeThreadId === activeThreadState.threadId) {
      if (activeThreadState.viewMode === 'live') {
        return;
      }

      if (activeThreadState.detailLoadState === 'loading') {
        return;
      }

      if (activeThreadState.detailLoadState === 'success' && activeThreadState.messages.length > 0) {
        return;
      }
    }

    let cancelled = false;

    activeThreadIdRef.current = routeThreadId;
    pendingTelemetryRequestIdsRef.current = {};
    pendingSuggestionRequestIdsRef.current = {};

    setThreadCollectionState((prev) => ({
      ...prev,
      error: '',
    }));
    setInput('');
    setSelectedFiles([]);
    setSelectedFileStatuses({});
    setAttachmentUploadState('idle');
    setAttachmentError('');
    setRepoBindingLoading(false);
    setRepoBindingError('');
    setMobileSidebarOpen(false);
    setAccountPanelOpen(false);
    setActiveThreadState({
      ...createInitialActiveThreadState(),
      threadId: routeThreadId,
      detailLoadState: 'loading',
    });
    setStreamSessionState(createInitialStreamSessionState());
    setActionSpaceState({
      ...createInitialActionSpaceState(),
      suggestedQueriesState: 'loading',
    });

    const hydrateThread = async () => {
      try {
        const detail = await fetchThreadDetail(routeThreadId);
        if (cancelled) {
          return;
        }

        activeThreadIdRef.current = routeThreadId;
        setActiveThreadState(createActiveThreadStateFromDetail(detail));
        setStreamSessionState(createHistoricalStreamSessionState(detail.thread.latest_status));
        setThreadCollectionState((prev) => ({
          ...prev,
          threads: upsertThreadSummary(prev.threads, detail.thread),
          error: '',
        }));
        void loadHistoricalTelemetry(routeThreadId);
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : 'Unknown error';
        activeThreadIdRef.current = '';
        setThreadCollectionState((prev) => ({
          ...prev,
          error: message,
        }));
        setActiveThreadState(createInitialActiveThreadState());
        setStreamSessionState(createInitialStreamSessionState());
        setActionSpaceState(createInitialActionSpaceState());
        router.replace('/');
      }
    };

    void hydrateThread();

    return () => {
      cancelled = true;
    };
  }, [
    routeThreadId,
    router,
    streamSessionState.isInterrupted,
    streamSessionState.loading,
  ]);
  /* eslint-enable react-hooks/exhaustive-deps */

  const handleAttachmentChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) {
      return;
    }

    const incomingFiles = Array.from(e.target.files);
    const validation = validateIncomingDraftFiles({
      existingFiles: selectedFiles,
      existingStatuses: selectedFileStatuses,
      incomingFiles,
    });
    setAttachmentUploadState(validation.message ? 'error' : 'idle');
    setAttachmentError(validation.message);
    if (validation.accepted.length > 0) {
      setSelectedFiles((prev) => [...prev, ...validation.accepted]);
      setSelectedFileStatuses((prev) => ({
        ...prev,
        ...validation.nextStatusPatch,
      }));
    }
    e.target.value = '';
  };

  const removeSelectedFile = (index: number) => {
    setSelectedFiles(prev => {
      const target = prev[index];
      if (target) {
        setSelectedFileStatuses((previous) => {
          const next = { ...previous };
          delete next[target.localKey];
          return next;
        });
      }
      return prev.filter((_, i) => i !== index);
    });
    setAttachmentUploadState('idle');
    setAttachmentError('');
  };

  const refreshThreadsSilently = async () => {
    try {
      const threads = await fetchThreads();
      setThreadCollectionState({
        threads,
        loadState: 'success',
        error: '',
      });
      setActiveThreadState((prev) => {
        const summary = threads.find((thread) => thread.thread_id === prev.threadId);
        if (!summary) {
          return prev;
        }

        return applyThreadSummaryToActiveThread(prev, summary);
      });
    } catch (error) {
      setThreadCollectionState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  };

  const ensureRepositoryThreadId = () => {
    if (activeThreadState.threadId) {
      return activeThreadState.threadId;
    }
    return `thread_${Date.now()}`;
  };

  const handleBindRepositoryUrl = async (
    sourceType: 'github_url' | 'git_url',
    sourceRef: string
  ) => {
    const threadId = ensureRepositoryThreadId();
    setRepoBindingLoading(true);
    setRepoBindingError('');
    try {
      const binding = await bindRepository({
        threadId,
        sourceType,
        sourceRef,
      });
      activeThreadIdRef.current = threadId;
      setActiveThreadState((prev) => ({
        ...prev,
        threadId,
        repoBinding: binding,
      }));
      if (routeThreadId !== threadId) {
        router.replace(buildThreadPath(threadId));
      }
      await refreshThreadsSilently();
    } catch (error) {
      setRepoBindingError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setRepoBindingLoading(false);
    }
  };

  const handleBindRepositoryZip = async (file: File) => {
    const threadId = ensureRepositoryThreadId();
    setRepoBindingLoading(true);
    setRepoBindingError('');
    try {
      const binding = await bindRepositoryZip({
        threadId,
        file,
      });
      activeThreadIdRef.current = threadId;
      setActiveThreadState((prev) => ({
        ...prev,
        threadId,
        repoBinding: binding,
      }));
      if (routeThreadId !== threadId) {
        router.replace(buildThreadPath(threadId));
      }
      await refreshThreadsSilently();
    } catch (error) {
      setRepoBindingError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setRepoBindingLoading(false);
    }
  };

  const handleDeleteRepositoryBinding = async () => {
    if (!activeThreadState.repoBinding) {
      return;
    }
    setRepoBindingLoading(true);
    setRepoBindingError('');
    try {
      await deleteRepositoryBinding(activeThreadState.repoBinding.id);
      setActiveThreadState((prev) => ({
        ...prev,
        repoBinding: null,
      }));
    } catch (error) {
      setRepoBindingError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setRepoBindingLoading(false);
    }
  };

  const handleMaterializeRepository = async () => {
    if (!activeThreadState.threadId) {
      return;
    }
    setRepoBindingLoading(true);
    setRepoBindingError('');
    try {
      await materializeRepository(activeThreadState.threadId);
    } catch (error) {
      setRepoBindingError(error instanceof Error ? error.message : 'Unknown error');
    } finally {
      setRepoBindingLoading(false);
    }
  };

  const handleStartNewChat = () => {
    if (isInteractionLocked) {
      return;
    }

    setInput('');
    setSelectedFiles([]);
    setSelectedFileStatuses({});
    setAttachmentUploadState('idle');
    setAttachmentError('');
    setRepoBindingLoading(false);
    setRepoBindingError('');
    setActiveThreadState(createInitialActiveThreadState());
    setStreamSessionState(createInitialStreamSessionState());
    setActionSpaceState(createInitialActionSpaceState());
    pendingTelemetryRequestIdsRef.current = {};
    pendingSuggestionRequestIdsRef.current = {};
    setMobileSidebarOpen(false);
    setAccountPanelOpen(false);
    router.push('/');
  };

  const applyGeneratedThreadTitle = (threadId: string, requestId: string, summary: { title: string }) => {
    if (pendingTitleRequestIdsRef.current[threadId] !== requestId) {
      return;
    }

    delete pendingTitleRequestIdsRef.current[threadId];
    setThreadCollectionState(prev => ({
      ...prev,
      threads: patchThreadSummary(prev.threads, threadId, { title: summary.title }),
    }));
    setActiveThreadState(prev => (
      prev.threadId === threadId
        ? { ...prev, title: summary.title || prev.title }
        : prev
    ));
  };

  const requestAiThreadTitleUpdate = (threadId: string, message?: string) => {
    const titleRequestId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    pendingTitleRequestIdsRef.current[threadId] = titleRequestId;
    void generateAiThreadTitle({
      threadId,
      message,
    })
      .then((summary) => {
        applyGeneratedThreadTitle(threadId, titleRequestId, summary);
      })
      .catch(() => {
        if (pendingTitleRequestIdsRef.current[threadId] === titleRequestId) {
          delete pendingTitleRequestIdsRef.current[threadId];
        }
      });
  };

  const applyThreadTelemetry = (
    threadId: string,
    requestId: string,
    telemetry: { reasoning_summary: string; suggested_queries: string[] }
  ) => {
    if (pendingTelemetryRequestIdsRef.current[threadId] !== requestId) {
      return;
    }

    delete pendingTelemetryRequestIdsRef.current[threadId];
    setActionSpaceState(prev => {
      if (activeThreadIdRef.current !== threadId) {
        return prev;
      }
      return {
        ...prev,
        reasoning: telemetry.reasoning_summary || prev.reasoning,
        reasoningEntries: telemetry.reasoning_summary
          ? [
              {
                id: `historical:${threadId}`,
                displayName: 'Saved Summary',
                content: telemetry.reasoning_summary,
              },
            ]
          : prev.reasoningEntries,
        suggestedQueries: telemetry.suggested_queries,
        suggestedQueriesState: telemetry.suggested_queries.length > 0 ? 'success' : 'idle',
        suggestedQueriesError: '',
      };
    });
  };

  const loadHistoricalTelemetry = async (threadId: string) => {
    const requestId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    pendingTelemetryRequestIdsRef.current[threadId] = requestId;

    try {
      const telemetry = await fetchThreadTelemetry(threadId);
      applyThreadTelemetry(threadId, requestId, telemetry);
      if (
        activeThreadIdRef.current === threadId &&
        telemetry.suggested_queries.length === 0
      ) {
        void requestSuggestedQueries(threadId);
      }
    } catch {
      if (pendingTelemetryRequestIdsRef.current[threadId] === requestId) {
        delete pendingTelemetryRequestIdsRef.current[threadId];
      }
      setActionSpaceState(prev => (
        activeThreadIdRef.current === threadId
          ? { ...prev, suggestedQueriesState: 'error', suggestedQueriesError: 'Failed to load historical telemetry.' }
          : prev
      ));
    }
  };

  const requestSuggestedQueries = async (threadId: string) => {
    const requestId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    pendingSuggestionRequestIdsRef.current[threadId] = requestId;
    setActionSpaceState(prev => (
      activeThreadIdRef.current === threadId
        ? { ...prev, suggestedQueriesState: 'loading', suggestedQueriesError: '' }
        : prev
    ));

    try {
      const telemetry = await generateSuggestedQueries({ threadId });
      if (pendingSuggestionRequestIdsRef.current[threadId] !== requestId) {
        return;
      }

      delete pendingSuggestionRequestIdsRef.current[threadId];
      setActionSpaceState(prev => (
        activeThreadIdRef.current === threadId
          ? {
              ...prev,
              suggestedQueries: telemetry.suggested_queries,
              suggestedQueriesState: telemetry.suggested_queries.length > 0 ? 'success' : 'idle',
              suggestedQueriesError: '',
            }
          : prev
      ));
    } catch {
      if (pendingSuggestionRequestIdsRef.current[threadId] === requestId) {
        delete pendingSuggestionRequestIdsRef.current[threadId];
      }
      setActionSpaceState(prev => (
        activeThreadIdRef.current === threadId
          ? { ...prev, suggestedQueriesState: 'error', suggestedQueriesError: 'Failed to generate follow-up prompts.' }
          : prev
      ));
    }
  };

  const handleRenameThread = async (threadId: string, title: string) => {
    const existingThread = threadCollectionState.threads.find((thread) => thread.thread_id === threadId);
    if (!existingThread) {
      return;
    }

    delete pendingTitleRequestIdsRef.current[threadId];

    setThreadCollectionState((prev) => ({
      ...prev,
      threads: patchThreadSummary(prev.threads, threadId, { title }),
    }));
    if (activeThreadState.threadId === threadId) {
      setActiveThreadState((prev) => ({ ...prev, title }));
    }

    try {
      const updatedThread = await patchThread({ threadId, title });
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, updatedThread),
      }));
      if (activeThreadState.threadId === threadId) {
        setActiveThreadState((prev) => applyThreadSummaryToActiveThread(prev, updatedThread));
      }
    } catch (error) {
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, existingThread),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      if (activeThreadState.threadId === threadId) {
        setActiveThreadState((prev) => ({ ...prev, title: existingThread.title }));
      }
    }
  };

  const handleTogglePinnedThread = async (threadId: string, pinned: boolean) => {
    const existingThread = threadCollectionState.threads.find((thread) => thread.thread_id === threadId);
    if (!existingThread) {
      return;
    }

    setThreadCollectionState((prev) => ({
      ...prev,
      threads: patchThreadSummary(prev.threads, threadId, { pinned }),
    }));

    try {
      const updatedThread = await patchThread({ threadId, pinned });
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, updatedThread),
      }));
      if (activeThreadState.threadId === threadId) {
        setActiveThreadState((prev) => applyThreadSummaryToActiveThread(prev, updatedThread));
      }
    } catch (error) {
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, existingThread),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  };

  const handleDeleteThread = async (threadId: string) => {
    const existingThread = threadCollectionState.threads.find((thread) => thread.thread_id === threadId);
    if (!existingThread) {
      return;
    }

    delete pendingTitleRequestIdsRef.current[threadId];

    const nextThreads = threadCollectionState.threads.filter((thread) => thread.thread_id !== threadId);
    const deletingActiveThread = activeThreadState.threadId === threadId;
    const previousActiveThreadState = activeThreadState;
    const previousStreamSessionState = streamSessionState;
    const previousActionSpaceState = actionSpaceState;

    setThreadCollectionState((prev) => ({
      ...prev,
      threads: prev.threads.filter((thread) => thread.thread_id !== threadId),
      error: '',
    }));
    if (deletingActiveThread) {
      activeThreadIdRef.current = '';
      setInput('');
      setSelectedFiles([]);
      setSelectedFileStatuses({});
      setAttachmentUploadState('idle');
      setAttachmentError('');
      setActiveThreadState(createInitialActiveThreadState());
      setStreamSessionState(createInitialStreamSessionState());
      setActionSpaceState(createInitialActionSpaceState());
      router.replace('/');
    }

    try {
      await deleteThread(threadId);
    } catch (error) {
      const restoredThreads = sortThreadSummaries([...nextThreads, existingThread]);

      setThreadCollectionState((prev) => ({
        ...prev,
        threads: restoredThreads,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      if (deletingActiveThread) {
        activeThreadIdRef.current = threadId;
        setActiveThreadState(previousActiveThreadState);
        setStreamSessionState(previousStreamSessionState);
        setActionSpaceState(previousActionSpaceState);
        router.replace(buildThreadPath(threadId));
      }
    }
  };

  const handleStreamEvent = (
    payload: StreamEvent,
    assistantMsgId: string,
    threadId: string
  ) => {
    // Collect all events for debug panel
    setActionSpaceState(prev => ({ ...prev, rawTraces: [...prev.rawTraces, payload] }));
    if (payload.event_type === 'status') {
      setThreadCollectionState(prev => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, {
          latest_status: payload.status,
          last_activity_at: payload.timestamp,
        }),
      }));

      setStreamSessionState(prev => {
        const nextState: StreamSessionState = {
          ...prev,
          loading: payload.status === 'running',
        };

        if (payload.status === 'completed') {
          return {
            ...nextState,
            currentNode: 'Completed',
            isInterrupted: false,
          };
        }

        if (payload.status === 'errored') {
          return {
            ...nextState,
            currentNode: 'Errored',
            isInterrupted: false,
            streamError: payload.message || prev.streamError,
          };
        }

        if (payload.status === 'interrupted') {
          return {
            ...nextState,
            currentNode: 'Requires User Action',
            isInterrupted: true,
            loading: false,
          };
        }

        if (payload.display_name) {
          return {
            ...nextState,
            currentNode: payload.display_name,
            isInterrupted: false,
          };
        }

        return nextState;
      });
      setActiveThreadState((prev) => ({
        ...prev,
        latestStatus: payload.status,
        lastActivityAt: payload.timestamp,
      }));
      return;
    }

    if (payload.event_type === 'route') {
      const nextDisplay = payload.display_name || payload.target || '';
      if (nextDisplay && payload.target !== 'FINISH') {
        setStreamSessionState(prev => ({
          ...prev,
          currentNode: nextDisplay,
          history: pushUniqueHistory(prev.history, nextDisplay),
        }));
      }
      return;
    }

    if (payload.event_type === 'tool_start') {
      const newTool: ToolExecution = {
        id: `tool_${toolIdCounterRef.current++}`,
        runId: payload.run_id,
        name: payload.display_name || payload.tool_name || payload.node || 'Tool',
        status: 'running',
        input: payload.input,
        startTime: Date.now(),
      };
      setActionSpaceState(prev => ({
        ...prev,
        toolExecutions: [...prev.toolExecutions, newTool],
      }));
      return;
    }

    if (payload.event_type === 'tool_end') {
      const targetName = payload.display_name || payload.tool_name || payload.node || 'Tool';
      setActionSpaceState(prev => {
        const next = [...prev.toolExecutions];
        let targetIndex = -1;

        if (payload.run_id) {
          for (let i = next.length - 1; i >= 0; i -= 1) {
            if (next[i].runId === payload.run_id && next[i].status === 'running') {
              targetIndex = i;
              break;
            }
          }
        }

        if (targetIndex === -1) {
          for (let i = next.length - 1; i >= 0; i -= 1) {
            if (next[i].name === targetName && next[i].status === 'running') {
              targetIndex = i;
              break;
            }
          }
        }

        if (targetIndex !== -1) {
          next[targetIndex] = {
            ...next[targetIndex],
            status: 'success',
            output: payload.output,
            endTime: Date.now(),
          };
        }

        return {
          ...prev,
          toolExecutions: next,
        };
      });
      return;
    }

    if (payload.event_type === 'tool_error') {
      const targetName = payload.display_name || payload.tool_name || payload.node || 'Tool';
      setActionSpaceState(prev => {
        const next = [...prev.toolExecutions];
        let targetIndex = -1;

        if (payload.run_id) {
          for (let i = next.length - 1; i >= 0; i -= 1) {
            if (next[i].runId === payload.run_id && next[i].status === 'running') {
              targetIndex = i;
              break;
            }
          }
        }

        if (targetIndex === -1) {
          for (let i = next.length - 1; i >= 0; i -= 1) {
            if (next[i].name === targetName && next[i].status === 'running') {
              targetIndex = i;
              break;
            }
          }
        }

        if (targetIndex !== -1) {
          next[targetIndex] = {
            ...next[targetIndex],
            status: 'error',
            output: payload.error,
            endTime: Date.now(),
          };
        }

        return {
          ...prev,
          toolExecutions: next,
        };
      });
      return;
    }

    if (payload.event_type === 'reasoning') {
      setActionSpaceState(prev => ({
        ...prev,
        reasoning: prev.reasoning + payload.content,
        reasoningEntries: appendReasoningEntry(prev.reasoningEntries, payload),
      }));
      return;
    }

    if (payload.event_type === 'text') {
      setThreadCollectionState(prev => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, {
          preview: payload.content.trim() || undefined,
          last_activity_at: payload.timestamp,
        }),
      }));
      setActiveThreadState(prev => ({
        ...prev,
        messages: appendAssistantText(prev.messages, assistantMsgId, payload.content),
        lastActivityAt: payload.timestamp,
      }));
      return;
    }

    if (payload.event_type === 'attachments') {
      setActiveThreadState(prev => {
        const nextMessages = [...prev.messages];
        for (let i = nextMessages.length - 1; i >= 0; i -= 1) {
          if (nextMessages[i].role === payload.role) {
            nextMessages[i] = {
              ...nextMessages[i],
              attachments: payload.attachments,
            };
            break;
          }
        }

        return {
          ...prev,
          messages: nextMessages,
        };
      });
      return;
    }

    if (payload.event_type === 'checkpoint') {
      setThreadCollectionState(prev => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, threadId, {
          checkpoint_id: payload.checkpoint_id || null,
        }),
      }));
      setActiveThreadState(prev => ({
        ...prev,
        checkpointId: payload.checkpoint_id || '',
      }));
      return;
    }

    if (payload.event_type === 'error') {
      setStreamSessionState(prev => ({
        ...prev,
        loading: false,
        currentNode: 'Errored',
        streamError: payload.message,
      }));
      setActiveThreadState(prev => ({
        ...prev,
        messages: appendAssistantText(
          prev.messages,
          `${assistantMsgId}_error`,
          `Error: ${payload.message}`
        ),
        latestStatus: 'errored',
      }));
    }
  };

  const handleSelectThread = async (threadId: string) => {
    if (isInteractionLocked) {
      return;
    }

    if (threadId === routeThreadId) {
      setMobileSidebarOpen(false);
      return;
    }

    router.push(buildThreadPath(threadId));
    setThreadCollectionState(prev => ({
      ...prev,
      error: '',
    }));
    setActiveThreadState({
      ...createInitialActiveThreadState(),
      threadId,
      detailLoadState: 'loading',
    });
    setStreamSessionState(createInitialStreamSessionState());
    setActionSpaceState({
      ...createInitialActionSpaceState(),
      suggestedQueriesState: 'loading',
    });
    setInput('');
    setSelectedFiles([]);
    setSelectedFileStatuses({});
    setAttachmentUploadState('idle');
    setAttachmentError('');
    setRepoBindingLoading(false);
    setRepoBindingError('');
    setMobileSidebarOpen(false);
    setAccountPanelOpen(false);

    try {
      const detail = await fetchThreadDetail(threadId);
      activeThreadIdRef.current = threadId;
      setActiveThreadState(createActiveThreadStateFromDetail(detail));
      setStreamSessionState(createHistoricalStreamSessionState(detail.thread.latest_status));
      setThreadCollectionState(prev => ({
        ...prev,
        threads: upsertThreadSummary(prev.threads, detail.thread),
        error: '',
      }));
      void loadHistoricalTelemetry(threadId);
    } catch (error) {
      setActiveThreadState(prev => ({
        ...prev,
        detailLoadState: 'error',
      }));
      setThreadCollectionState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      router.replace('/');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const readyDraftItems = selectedFiles.filter(
      (item) => selectedFileStatuses[item.localKey]?.status !== 'failed'
    );
    if ((!input.trim() && readyDraftItems.length === 0) || isInteractionLocked) return;

    const submittedInput = input;
    const isNewThread = !activeThreadState.threadId;
    const thread_id = activeThreadState.threadId || `thread_${Date.now()}`;
    const nextThreadTurnCount =
      activeThreadState.messages.filter(
        (message) =>
          message.role === 'user' &&
          !message.content.startsWith('[User Action]:')
      ).length + 1;
    const existingThread = threadCollectionState.threads.find(
      (thread) => thread.thread_id === thread_id
    );
    const readyLocalKeys = readyDraftItems.map((item) => item.localKey);
    let uploadedAttachmentIds: string[] = [];
    let successfulDraftFiles = readyDraftItems.map((item) => item.file);

    try {
      if (readyDraftItems.length > 0) {
        setAttachmentUploadState('uploading');
        setAttachmentError('');
        setSelectedFileStatuses((prev) => {
          const next = { ...prev };
          for (const item of readyDraftItems) {
            next[item.localKey] = { status: 'uploading' };
          }
          return next;
        });

        const uploadResult = await uploadChatAttachments({
          threadId: thread_id,
          files: readyDraftItems.map((item) => item.file),
        });

        const failedIndexes = new Map(
          uploadResult.errors.map((error) => [error.input_index, error])
        );
        const successfulDraftItems = readyDraftItems.filter(
          (_, index) => !failedIndexes.has(index)
        );
        successfulDraftFiles = successfulDraftItems.map((item) => item.file);
        uploadedAttachmentIds = uploadResult.uploads.map((attachment) => attachment.id);

        setSelectedFiles((prev) =>
          prev.filter((item) => {
            if (!readyLocalKeys.includes(item.localKey)) {
              return true;
            }
            return !successfulDraftItems.some(
              (successfulItem) => successfulItem.localKey === item.localKey
            );
          })
        );
        setSelectedFileStatuses((prev) => {
          const next = { ...prev };
          for (const item of successfulDraftItems) {
            delete next[item.localKey];
          }
          for (const [index, error] of failedIndexes) {
            const failedItem = readyDraftItems[index];
            if (failedItem) {
              next[failedItem.localKey] = {
                status: 'failed',
                error: error.detail,
              };
            }
          }
          return next;
        });

        if (uploadResult.errors.length > 0) {
          setAttachmentUploadState('error');
          setAttachmentError(summarizeUploadErrors(uploadResult.errors));
        } else {
          setAttachmentUploadState('idle');
          setAttachmentError('');
        }

        if (readyDraftItems.length > 0 && successfulDraftFiles.length === 0) {
          return;
        }
      }

      const userAttachments = buildOptimisticAttachments(successfulDraftFiles);
      const userMessage: ChatMessage = {
        role: 'user',
        content: submittedInput,
        id: Date.now().toString(),
        attachments: userAttachments,
      };
      const optimisticThread = createOptimisticThreadSummary({
        threadId: thread_id,
        content: submittedInput,
        existingThread,
      });
      delete pendingTelemetryRequestIdsRef.current[thread_id];
      delete pendingSuggestionRequestIdsRef.current[thread_id];

      setActiveThreadState(prev => ({
        ...prev,
        threadId: thread_id,
        title: prev.title || optimisticThread.title,
        checkpointId: '',
        messages: [...prev.messages, userMessage],
        detailLoadState: 'success',
        latestStatus: 'running',
        lastActivityAt: optimisticThread.last_activity_at,
        viewMode: 'live',
      }));
      setThreadCollectionState(prev => ({
        ...prev,
        threads: upsertThreadSummary(prev.threads, optimisticThread),
        error: '',
      }));
      activeThreadIdRef.current = thread_id;
      setInput('');
      setMobileSidebarOpen(false);
      setStreamSessionState({
        ...createInitialStreamSessionState(),
        loading: true,
      });
      setActionSpaceState(createInitialActionSpaceState());

      const stream = await sendChatStream({
        message: submittedInput,
        threadId: thread_id,
        attachmentIds:
          uploadedAttachmentIds.length > 0 ? uploadedAttachmentIds : undefined,
      });

      if (isNewThread) {
        router.replace(buildThreadPath(thread_id));
      }

      if (isNewThread) {
        requestAiThreadTitleUpdate(thread_id, submittedInput);
      }

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      const assistantMsgId = Date.now().toString() + "_ai";
      let buffer = '';
      let turnCompleted = false;

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const { blocks, remainder } = splitSseBlocks(buffer);
        buffer = remainder;

        for (const block of blocks) {
          const payload = parseSseBlock(block) as StreamEvent | null;
          if (payload) {
            if (payload.event_type === 'status' && payload.status === 'completed') {
              turnCompleted = true;
            }
            handleStreamEvent(payload, assistantMsgId, thread_id);
          }
        }

        if (done) {
          if (buffer.trim()) {
            const finalPayload = parseSseBlock(buffer) as StreamEvent | null;
            if (finalPayload) {
              if (finalPayload.event_type === 'status' && finalPayload.status === 'completed') {
                turnCompleted = true;
              }
              handleStreamEvent(finalPayload, assistantMsgId, thread_id);
            }
          }
          setStreamSessionState(prev => ({
            ...prev,
            loading: false,
          }));
          await refreshThreadsSilently();
          if (nextThreadTurnCount >= 5) {
            requestAiThreadTitleUpdate(thread_id);
          }
          if (turnCompleted) {
            void requestSuggestedQueries(thread_id);
          }
          break;
        }
      }
    } catch (err) {
      console.error(err);
      const failureTimestamp = new Date().toISOString();
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setAttachmentUploadState('error');
      setAttachmentError(errorMessage);
      setSelectedFileStatuses((prev) => {
        const next = { ...prev };
        for (const item of readyDraftItems) {
          next[item.localKey] = {
            status: 'failed',
            error: errorMessage,
          };
        }
        return next;
      });
      setStreamSessionState(prev => ({
        ...prev,
        loading: false,
        currentNode: 'Errored',
        streamError: errorMessage,
      }));
      setThreadCollectionState(prev => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, thread_id, {
          latest_status: 'errored',
          last_activity_at: failureTimestamp,
        }),
      }));
      setActiveThreadState(prev => ({
        ...prev,
        latestStatus: 'errored',
        lastActivityAt: failureTimestamp,
        messages: appendAssistantText(
          prev.messages,
          `${thread_id}_request_error`,
          `Error: ${errorMessage}`
        ),
      }));
    }
  };

  const handleResume = async (action: string, feedback: string) => {
    if (!activeThreadState.threadId) return;

    const resumeText = `[User Action]: ${action}${feedback ? `\nFeedback: ${feedback}` : ''}`;
    const resumeMessage: ChatMessage = {
      role: 'user',
      content: resumeText,
      id: `${Date.now()}_resume_user`,
    };
    const existingThread = threadCollectionState.threads.find(
      (thread) => thread.thread_id === activeThreadState.threadId
    );
    const optimisticThread = createOptimisticThreadSummary({
      threadId: activeThreadState.threadId,
      content: resumeText,
      existingThread,
    });
    const previousMessages = activeThreadState.messages;
    const previousLatestStatus = activeThreadState.latestStatus;
    const previousLastActivityAt = activeThreadState.lastActivityAt;
    const previousCheckpointId = activeThreadState.checkpointId;
    const previousViewMode = activeThreadState.viewMode;
    const previouslyInterrupted =
      streamSessionState.isInterrupted || activeThreadState.latestStatus === 'interrupted';

    setMobileSidebarOpen(false);
    setThreadCollectionState(prev => ({
      ...prev,
      threads: upsertThreadSummary(prev.threads, optimisticThread),
      error: '',
    }));
    setActiveThreadState(prev => ({
      ...prev,
      messages: [...prev.messages, resumeMessage],
      latestStatus: 'running',
      lastActivityAt: optimisticThread.last_activity_at,
      viewMode: 'live',
    }));
    setStreamSessionState(prev => ({
      ...prev,
      isInterrupted: false,
      loading: true,
      currentNode: 'Resuming...',
      streamError: '',
    }));
    activeThreadIdRef.current = activeThreadState.threadId;
    let receivedStreamEvent = false;

    try {
      const stream = await resumeChatStream({
        threadId: activeThreadState.threadId,
        action,
        feedback,
      });

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      const assistantMsgId = Date.now().toString() + "_ai_resume";
      let buffer = '';
      let turnCompleted = false;

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const { blocks, remainder } = splitSseBlocks(buffer);
        buffer = remainder;

        for (const block of blocks) {
          const payload = parseSseBlock(block) as StreamEvent | null;
          if (payload) {
            receivedStreamEvent = true;
            if (payload.event_type === 'status' && payload.status === 'completed') {
              turnCompleted = true;
            }
            handleStreamEvent(payload, assistantMsgId, activeThreadState.threadId);
          }
        }

        if (done) {
          if (buffer.trim()) {
            const finalPayload = parseSseBlock(buffer) as StreamEvent | null;
            if (finalPayload) {
              receivedStreamEvent = true;
              if (finalPayload.event_type === 'status' && finalPayload.status === 'completed') {
                turnCompleted = true;
              }
              handleStreamEvent(finalPayload, assistantMsgId, activeThreadState.threadId);
            }
          }
          setStreamSessionState(prev => ({
            ...prev,
            loading: false,
          }));
          await refreshThreadsSilently();
          if (turnCompleted) {
            void requestSuggestedQueries(activeThreadState.threadId);
          }
          break;
        }
      }
    } catch (err) {
      console.error(err);
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      const failureTimestamp = new Date().toISOString();
      const shouldRestoreInterruptedState = !receivedStreamEvent && previouslyInterrupted;

      setStreamSessionState(prev => ({
        ...prev,
        loading: false,
        currentNode: shouldRestoreInterruptedState ? 'Requires User Action' : 'Errored',
        streamError: errorMessage,
        isInterrupted: shouldRestoreInterruptedState,
      }));
      setThreadCollectionState(prev => ({
        ...prev,
        threads:
          shouldRestoreInterruptedState && existingThread
            ? upsertThreadSummary(prev.threads, existingThread)
            : patchThreadSummary(prev.threads, activeThreadState.threadId, {
                latest_status: 'errored',
                last_activity_at: failureTimestamp,
              }),
      }));
      setActiveThreadState(prev => ({
        ...prev,
        checkpointId: shouldRestoreInterruptedState ? previousCheckpointId : prev.checkpointId,
        latestStatus: shouldRestoreInterruptedState ? previousLatestStatus : 'errored',
        lastActivityAt: shouldRestoreInterruptedState ? previousLastActivityAt : failureTimestamp,
        viewMode: shouldRestoreInterruptedState ? previousViewMode : prev.viewMode,
        messages: shouldRestoreInterruptedState
          ? previousMessages
          : appendAssistantText(
              prev.messages,
              `${activeThreadState.threadId}_resume_error`,
              `Error: ${errorMessage}`
            ),
      }));
    }
  };

  const latestThreadMessage = activeThreadState.messages[activeThreadState.messages.length - 1];
  const latestAssistantMessageId =
    latestThreadMessage?.role === 'assistant' ? latestThreadMessage.id : undefined;
  const hasSendableAttachments = selectedFiles.some(
    (item) => selectedFileStatuses[item.localKey]?.status !== 'failed'
  );

  const handleSuggestedQuerySelect = (query: string) => {
    setInput(query);
  };

  const liveReasoningFallback = (() => {
    if (actionSpaceState.reasoning.trim() || isHistoricalView) {
      return '';
    }

    if (activeThreadState.viewMode === 'draft' && activeThreadState.messages.length === 0) {
      return '';
    }

    const mostRecentTool = [...actionSpaceState.toolExecutions]
      .reverse()
      .find((tool) => tool.status === 'running' || tool.status === 'success');
    if (mostRecentTool) {
      if (mostRecentTool.status === 'running') {
        return `${mostRecentTool.name} 도구 결과를 바탕으로 응답 근거를 정리하는 중입니다.`;
      }
      return `${mostRecentTool.name} 결과를 반영해 최종 답변의 핵심 근거를 정리했습니다.`;
    }

    if (streamSessionState.currentNode) {
      if (streamSessionState.loading) {
        return `${streamSessionState.currentNode} 단계에서 현재 요청에 맞는 답변 구조를 잡는 중입니다.`;
      }
      return `${streamSessionState.currentNode} 단계에서 이번 turn의 답변 구성이 마무리되었습니다.`;
    }

    return '현재 요청을 해석하고 다음 응답 단계를 정리하는 중입니다.';
  })();

  const shouldShowStandaloneToolStrip =
    streamSessionState.loading &&
    !isHistoricalView &&
    !latestAssistantMessageId &&
    (actionSpaceState.toolExecutions.length > 0 || Boolean(streamSessionState.currentNode));

  const sidebarContent = (
    <ThreadListSidebar
      threads={threadCollectionState.threads}
      loadState={threadCollectionState.loadState}
      error={threadCollectionState.error}
      selectedThreadId={activeThreadState.threadId}
      disabled={isInteractionLocked}
      onNewChat={handleStartNewChat}
      onSelectThread={handleSelectThread}
      onRenameThread={handleRenameThread}
      onTogglePinnedThread={handleTogglePinnedThread}
      onDeleteThread={handleDeleteThread}
    />
  );

  return (
    <main className="relative flex h-screen flex-col overflow-hidden bg-[var(--oa-bg)] text-[var(--oa-copy)]">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-10%] top-[-8%] h-[32rem] w-[32rem] rounded-full bg-[rgba(143,245,255,0.08)] blur-[120px]" />
        <div className="absolute bottom-[-16%] right-[-8%] h-[28rem] w-[28rem] rounded-full bg-[rgba(172,137,255,0.12)] blur-[120px]" />
      </div>

      {accountPanelOpen ? (
        <AccountDrawer
          user={currentUser}
          onClose={() => setAccountPanelOpen(false)}
          onLogout={onLogout}
          onUserUpdated={onUserUpdated}
        />
      ) : null}

      <WorkspaceTopNav
        activeSection="chat"
        currentUser={currentUser}
        onOpenAccountDrawer={() => setAccountPanelOpen(true)}
        onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
      />

      <div className="relative z-10 flex min-h-0 flex-1 overflow-hidden">
      <aside className="hidden h-full w-64 shrink-0 border-r border-[rgba(255,255,255,0.05)] bg-[rgba(17,19,26,0.96)] py-6 lg:flex lg:flex-col">
        {sidebarContent}
      </aside>

      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden">
          <button
            type="button"
            aria-label="Close thread sidebar"
            onClick={() => setMobileSidebarOpen(false)}
            className="absolute inset-0 bg-[rgba(7,9,13,0.78)] backdrop-blur-sm"
          />

          <div className="absolute inset-y-0 left-0 flex w-[min(24rem,92vw)] flex-col border-r border-[rgba(255,255,255,0.06)] bg-[rgba(17,19,26,0.98)] py-6 shadow-2xl shadow-black/50">
            <div className="mb-4 flex items-center justify-between px-6">
              <div>
                <div className="font-[var(--font-display)] text-[20px] font-bold text-[#00f0ff]">
                  OrchAgent
                </div>
                <div className="text-[10px] uppercase tracking-[0.22em] text-[rgba(170,170,179,0.7)]">
                  Chat Workspace
                </div>
              </div>
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(false)}
                className="rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.4)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0]"
              >
                <X size={16} />
              </button>
            </div>
            {sidebarContent}
          </div>
        </div>
      ) : null}

      <section className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 md:px-8">
          <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8">
            {activeThreadState.detailLoadState === 'loading' ? (
              <div className="flex min-h-[16rem] items-center justify-center">
                <div className="rounded-[16px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.5)] px-6 py-5 text-sm text-[rgba(231,231,240,0.88)] shadow-xl">
                  <div className="flex items-center gap-3">
                    <Loader2 size={18} className="animate-spin text-[#8ff5ff]" />
                    <span>Loading thread history...</span>
                  </div>
                </div>
              </div>
            ) : null}

            {activeThreadState.detailLoadState !== 'loading' && activeThreadState.messages.length === 0 ? (
              <div className="mx-auto flex min-h-[26rem] max-w-md flex-col items-center justify-center text-center">
                <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-[20px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.5)] shadow-xl">
                  <Bot size={36} className="text-[#8ff5ff]" />
                </div>
                <h2 className="font-[var(--font-display)] text-[28px] font-bold text-[#e7e7f0]">
                  System Ready
                </h2>
                <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.78)]">
                  Initiate a hierarchical task. The orchestration workspace will reveal reasoning summaries, tool activity, and follow-up prompts in context.
                </p>
              </div>
            ) : null}

            {activeThreadState.detailLoadState !== 'loading'
              ? activeThreadState.messages.map((message) => {
                  const isUser = message.role === 'user';
                  const showToolStatuses =
                    !isUser &&
                    !isHistoricalView &&
                    message.id === latestAssistantMessageId &&
                    actionSpaceState.toolExecutions.length > 0;

                  return (
                    <div
                      key={message.id}
                      className={cn(
                        'animate-in fade-in slide-in-from-bottom-2 duration-300',
                        isUser ? 'ml-auto flex w-full justify-end' : 'flex w-full justify-start'
                      )}
                    >
                      {isUser ? (
                        <div className="flex w-full max-w-[520px] flex-col items-end">
                          <MessageAttachmentStrip
                            attachments={message.attachments || []}
                            align="end"
                            onImageSelect={setLightboxAttachment}
                          />
                          {message.content.trim() ? (
                            <div className="rounded-bl-[14px] rounded-br-[14px] rounded-tl-[14px] border border-[rgba(143,245,255,0.14)] bg-[rgba(35,38,46,0.28)] px-4 py-3 text-[13px] leading-6 text-[#e7e7f0] backdrop-blur-[12px]">
                              {message.content}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div className="flex w-full max-w-[680px] items-start gap-4">
                          <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[#7000ff] text-white shadow-[0px_0px_0px_2px_rgba(172,137,255,0.2)]">
                            <Bot size={14} />
                          </div>
                          <div className="flex min-w-0 flex-1 flex-col gap-3">
                            {showToolStatuses ? (
                              <LiveToolStatusStrip
                                toolExecutions={actionSpaceState.toolExecutions}
                                currentNode={streamSessionState.currentNode}
                                loading={streamSessionState.loading}
                              />
                            ) : null}
                            <MessageAttachmentStrip
                              attachments={message.attachments || []}
                              align="start"
                              onImageSelect={setLightboxAttachment}
                            />
                            <div className="px-1 py-1 text-[14px] leading-7 text-[#e7e7f0]">
                              <MarkdownContent content={message.content} />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              : null}

            {streamSessionState.loading ? (
              <div className="flex w-full justify-start">
                <div className="flex w-full max-w-[680px] items-start gap-4">
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[#7000ff] text-white shadow-[0px_0px_0px_2px_rgba(172,137,255,0.2)]">
                    <Bot size={14} />
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col gap-3">
                    {shouldShowStandaloneToolStrip ? (
                      <LiveToolStatusStrip
                        toolExecutions={actionSpaceState.toolExecutions}
                        currentNode={streamSessionState.currentNode}
                        loading={streamSessionState.loading}
                      />
                    ) : null}
                    <div className="px-1 py-1 text-[14px] italic text-[rgba(170,170,179,0.9)]">
                      {streamSessionState.currentNode || 'Coordinating team...'}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {streamSessionState.isInterrupted ? (
              <div className="flex w-full justify-start">
                <div className="flex w-full max-w-[680px] items-start gap-4">
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(245,158,11,0.14)] text-amber-300">
                    <Bot size={14} />
                  </div>
                  <div className="w-full">
                    <HITLPanel onAction={handleResume} loading={streamSessionState.loading} />
                  </div>
                </div>
              </div>
            ) : null}

            {!!streamSessionState.streamError && !streamSessionState.loading ? (
              <div className="flex w-full justify-start">
                <div className="flex w-full max-w-[680px] items-start gap-4">
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(239,68,68,0.14)] text-red-300">
                    <Bot size={14} />
                  </div>
                  <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-200">
                    {streamSessionState.streamError}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="border-t border-[rgba(255,255,255,0.05)] bg-[rgba(29,31,40,0.8)] px-6 py-6 backdrop-blur-xl md:px-8">
          <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-[720px] flex-col gap-3">
            <SelectedAttachmentTray
              files={selectedFiles}
              statuses={selectedFileStatuses}
              uploadState={attachmentUploadState}
              error={attachmentError}
              onRemove={removeSelectedFile}
            />

            <div className="relative">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Message OrchAgent..."
                className="w-full rounded-[16px] border border-[rgba(255,255,255,0.1)] bg-black px-14 py-4 pr-32 text-[14px] text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.3)]"
                disabled={isInteractionLocked}
              />
              <button
                type="button"
                aria-label="Add files"
                onClick={() => fileInputRef.current?.click()}
                disabled={isInteractionLocked}
                className="absolute left-3 top-1/2 -translate-y-1/2 p-2 text-[rgba(170,170,179,0.72)] transition hover:text-[#8ff5ff] disabled:text-slate-800"
              >
                <Paperclip size={18} />
              </button>
              <input
                type="file"
                multiple
                accept="image/*,.pdf,.xlsx,.csv,.json,.docx"
                className="hidden"
                ref={fileInputRef}
                onChange={handleAttachmentChange}
              />
              <button
                type="submit"
                aria-label="Send message"
                disabled={isInteractionLocked || (!input.trim() && !hasSendableAttachments)}
                className="absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center justify-center rounded-[12px] bg-[#8ff5ff] px-5 py-2.5 text-[12px] font-bold uppercase tracking-[0.18em] text-[#005d63] shadow-[0px_10px_15px_-3px_rgba(143,245,255,0.2),0px_4px_6px_-4px_rgba(143,245,255,0.2)] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-600"
              >
                {streamSessionState.loading ? <Loader2 className="animate-spin" size={16} /> : 'Send'}
              </button>
            </div>

            <RepositoryBindingPanel
              binding={activeThreadState.repoBinding}
              disabled={isInteractionLocked}
              loading={repoBindingLoading}
              error={repoBindingError}
              onBindUrl={handleBindRepositoryUrl}
              onBindZip={handleBindRepositoryZip}
              onDeleteBinding={handleDeleteRepositoryBinding}
              onMaterialize={handleMaterializeRepository}
            />
          </form>
        </div>
      </section>

      <ImageLightbox
        attachment={lightboxAttachment}
        onClose={() => setLightboxAttachment(null)}
      />

      <aside
        ref={actionSpaceRef}
        className="hidden w-[404px] shrink-0 border-l border-[rgba(255,255,255,0.05)] bg-[rgba(12,14,20,0.78)] px-6 py-6 backdrop-blur-xl xl:flex xl:flex-col xl:overflow-y-auto"
      >
        <div className="space-y-6">
          <AgentTimeline
            history={streamSessionState.history}
            currentNode={streamSessionState.currentNode}
            loading={streamSessionState.loading}
            historicalView={isHistoricalView}
          />

          <ReasoningSummaryPanel
            content={actionSpaceState.reasoning}
            entries={actionSpaceState.reasoningEntries}
            isThinking={streamSessionState.loading}
            historicalView={isHistoricalView}
            fallbackSummary={liveReasoningFallback}
          />

          <SuggestedQueriesPanel
            queries={actionSpaceState.suggestedQueries}
            loadState={actionSpaceState.suggestedQueriesState}
            onSelectQuery={handleSuggestedQuerySelect}
            historicalView={isHistoricalView}
          />

        </div>
      </aside>
      </div>
    </main>
  );
}

export default function WorkspaceRouteRoot() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading, refreshUser, updateUser, logout } = useAuth();
  const routeThreadId = deriveRouteThreadId(pathname);

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [loading, router, user]);

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  if (loading) {
    return <AuthLoadingScreen message="Loading your workspace..." />;
  }

  if (!user) {
    return <AuthLoadingScreen message="Redirecting to login..." />;
  }

  if (user.must_change_password) {
    return (
      <MustChangePasswordView
        currentUser={user}
        onPasswordChanged={refreshUser}
        onLogout={handleLogout}
      />
    );
  }

  return (
    <WorkspaceApp
      currentUser={user}
      onLogout={handleLogout}
      onUserUpdated={updateUser}
      routeThreadId={routeThreadId}
    />
  );
}
