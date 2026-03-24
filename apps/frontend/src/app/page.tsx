"use client";

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Send, Terminal, Loader2, Bot, Image as ImageIcon, X, ChevronDown, Menu, Bell, PanelRightOpen } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import NextImage from 'next/image';
import { ChatMessage, StreamEvent, ToolExecution } from '@/types/agent';
import type { AuthUser } from '@/types/auth';
import type { ActionSpaceState, ActiveThreadState, StreamSessionState, ThreadCollectionState } from '@/types/thread';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { changePasswordUser, deleteThread, fetchThreadDetail, fetchThreadTelemetry, fetchThreads, generateAiThreadTitle, generateSuggestedQueries, patchThread, resumeChatStream, sendChatStream } from '@/lib/api';
import { appendAssistantText, parseSseBlock, pushUniqueHistory, splitSseBlocks } from '@/lib/chat-stream';
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

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
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
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

// --- Helper Functions ---
const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        // Remove data:image/...;base64, prefix
        resolve(reader.result.split(',')[1]);
      }
    };
    reader.onerror = error => reject(error);
  });
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
}: {
  currentUser: AuthUser;
  onLogout: () => Promise<void> | void;
  onUserUpdated: (user: AuthUser) => void;
}) {
  const [input, setInput] = useState('');
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
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
    streamSessionState.isInterrupted ||
    activeThreadState.detailLoadState === 'loading';
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

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedImages(prev => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const removeImage = (index: number) => {
    setSelectedImages(prev => prev.filter((_, i) => i !== index));
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

  const handleStartNewChat = () => {
    if (isInteractionLocked) {
      return;
    }

    setInput('');
    setSelectedImages([]);
    setActiveThreadState(createInitialActiveThreadState());
    setStreamSessionState(createInitialStreamSessionState());
    setActionSpaceState(createInitialActionSpaceState());
    pendingTelemetryRequestIdsRef.current = {};
    pendingSuggestionRequestIdsRef.current = {};
    setMobileSidebarOpen(false);
    setAccountPanelOpen(false);
  };

  const applyGeneratedThreadTitle = (threadId: string, requestId: string, summary: { title: string }) => {
    if (pendingTitleRequestIdsRef.current[threadId] !== requestId) {
      return;
    }

    delete pendingTitleRequestIdsRef.current[threadId];
    delete pendingTelemetryRequestIdsRef.current[threadId];
    delete pendingSuggestionRequestIdsRef.current[threadId];
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
      setInput('');
      setSelectedImages([]);
      setActiveThreadState(createInitialActiveThreadState());
      setStreamSessionState(createInitialStreamSessionState());
      setActionSpaceState(createInitialActionSpaceState());
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
        setActiveThreadState(previousActiveThreadState);
        setStreamSessionState(previousStreamSessionState);
        setActionSpaceState(previousActionSpaceState);
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

    if (threadId === activeThreadState.threadId && activeThreadState.messages.length > 0) {
      setMobileSidebarOpen(false);
      return;
    }

    setThreadCollectionState(prev => ({
      ...prev,
      error: '',
    }));
    setActiveThreadState(prev => ({
      ...prev,
      detailLoadState: 'loading',
    }));
    setActionSpaceState({
      ...createInitialActionSpaceState(),
      suggestedQueriesState: 'loading',
    });

    try {
      const detail = await fetchThreadDetail(threadId);
      activeThreadIdRef.current = threadId;
      setActiveThreadState(createActiveThreadStateFromDetail(detail));
      setStreamSessionState(createHistoricalStreamSessionState(detail.thread.latest_status));
      setThreadCollectionState(prev => ({
        ...prev,
        threads: patchThreadSummary(prev.threads, detail.thread.thread_id, detail.thread),
        error: '',
      }));
      setInput('');
      setSelectedImages([]);
      setMobileSidebarOpen(false);
      setAccountPanelOpen(false);
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
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && selectedImages.length === 0) || isInteractionLocked) return;

    const submittedInput = input;
    const isNewThread = !activeThreadState.threadId;
    const thread_id = activeThreadState.threadId || `thread_${Date.now()}`;
    const userMessage: ChatMessage = { role: 'user', content: submittedInput, id: Date.now().toString() };

    // Convert images to base64
    const base64Images = await Promise.all(selectedImages.map(fileToBase64));
    const existingThread = threadCollectionState.threads.find(
      (thread) => thread.thread_id === thread_id
    );
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
    setSelectedImages([]);
    setMobileSidebarOpen(false);
    setStreamSessionState({
      ...createInitialStreamSessionState(),
      loading: true,
    });
    setActionSpaceState(createInitialActionSpaceState());

    try {
      const stream = await sendChatStream({
        message: submittedInput,
        threadId: thread_id,
        images: base64Images,
      });

      if (isNewThread) {
        const titleRequestId = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
        pendingTitleRequestIdsRef.current[thread_id] = titleRequestId;
        void generateAiThreadTitle({
          threadId: thread_id,
          message: submittedInput,
        })
          .then((summary) => {
            applyGeneratedThreadTitle(thread_id, titleRequestId, summary);
          })
          .catch(() => {
            if (pendingTitleRequestIdsRef.current[thread_id] === titleRequestId) {
              delete pendingTitleRequestIdsRef.current[thread_id];
            }
          });
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

  const latestAssistantMessageId = [...activeThreadState.messages]
    .reverse()
    .find((message) => message.role === 'assistant')?.id;

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

      <header className="relative z-20 flex h-16 shrink-0 items-center justify-between border-b border-[rgba(255,255,255,0.05)] bg-[rgba(12,14,20,0.9)] px-6 backdrop-blur-xl md:px-8">
        <div className="flex min-w-0 items-center gap-4">
          <button
            type="button"
            onClick={() => setMobileSidebarOpen(true)}
            className="inline-flex rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.4)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0] lg:hidden"
          >
            <Menu size={16} />
          </button>

          <div className="hidden items-center gap-8 md:flex">
            <div className="font-[var(--font-display)] text-[24px] font-bold tracking-[-0.04em] text-[#00f0ff]">
              OrchAgent
            </div>

            <nav className="flex items-center gap-2 text-[14px]">
              <button
                type="button"
                className="rounded-[8px] border-b-2 border-[#00f0ff] px-3 py-1 font-[var(--font-display)] text-[#00f0ff]"
              >
                Chat
              </button>
              <button
                type="button"
                aria-disabled="true"
                className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
              >
                Dashboard
              </button>
              <button
                type="button"
                aria-disabled="true"
                className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
              >
                Agents
              </button>
              <button
                type="button"
                aria-disabled="true"
                className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
              >
                Logs
              </button>
              <button
                type="button"
                aria-disabled="true"
                className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
              >
                Settings
              </button>
            </nav>
          </div>

          <div className="md:hidden">
            <div className="font-[var(--font-display)] text-[18px] font-bold text-[#00f0ff]">
              OrchAgent
            </div>
          </div>
        </div>

        <div className="flex min-w-0 items-center gap-3">
          <div className="hidden min-w-0 items-center gap-3 rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.45)] px-3 py-2 sm:flex">
            <div className="min-w-0">
              <div className="truncate text-[12px] font-semibold text-[#e7e7f0]">
                {activeThreadState.title || 'New Chat'}
              </div>
              <div className="truncate text-[10px] uppercase tracking-[0.22em] text-[rgba(170,170,179,0.72)]">
                {activeThreadState.threadId || 'draft_session'}
              </div>
            </div>
          </div>

          <button
            type="button"
            aria-label="Notifications"
            className="hidden rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.45)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0] sm:inline-flex"
          >
            <Bell size={16} />
          </button>

            <button
              type="button"
              aria-label="Open account drawer"
              onClick={() => setAccountPanelOpen(true)}
            className="inline-flex items-center gap-2 rounded-[12px] border border-[rgba(143,245,255,0.16)] bg-[rgba(29,31,40,0.45)] px-3 py-2 text-[12px] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.3)]"
            >
            <PanelRightOpen size={15} className="text-[#8ff5ff]" />
            <span className="hidden font-semibold sm:inline">
              {currentUser.display_name || currentUser.login_id}
            </span>
          </button>
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1 overflow-hidden">
      {accountPanelOpen ? (
        <AccountDrawer
          user={currentUser}
          onClose={() => setAccountPanelOpen(false)}
          onLogout={onLogout}
          onUserUpdated={onUserUpdated}
        />
      ) : null}

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
                        <div className="max-w-[540px] rounded-bl-[16px] rounded-br-[16px] rounded-tl-[16px] border border-[rgba(143,245,255,0.2)] bg-[rgba(35,38,46,0.4)] px-5 py-4 text-[14px] leading-7 text-[#e7e7f0] backdrop-blur-md">
                          {message.content}
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
                  <div className="px-1 py-1 text-[14px] italic text-[rgba(170,170,179,0.9)]">
                    {streamSessionState.currentNode || 'Coordinating team...'}
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
            {selectedImages.length > 0 ? (
              <div className="flex flex-wrap gap-2 rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.4)] p-3">
                {selectedImages.map((file, i) => (
                  <div key={i} className="relative h-16 w-16 overflow-hidden rounded-[10px] border border-[rgba(255,255,255,0.08)]">
                    <NextImage
                      src={URL.createObjectURL(file)}
                      alt="preview"
                      width={64}
                      height={64}
                      className="h-full w-full object-cover"
                      unoptimized
                    />
                    <button
                      type="button"
                      onClick={() => removeImage(i)}
                      className="absolute right-1 top-1 rounded-full bg-[rgba(7,9,13,0.84)] p-1 text-white transition hover:bg-red-500"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            ) : null}

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
                aria-label="Attach image"
                onClick={() => fileInputRef.current?.click()}
                disabled={isInteractionLocked}
                className="absolute left-3 top-1/2 -translate-y-1/2 p-2 text-[rgba(170,170,179,0.72)] transition hover:text-[#8ff5ff] disabled:text-slate-800"
              >
                <ImageIcon size={18} />
              </button>
              <input
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                ref={fileInputRef}
                onChange={handleImageChange}
              />
              <button
                type="submit"
                aria-label="Send message"
                disabled={isInteractionLocked || (!input.trim() && selectedImages.length === 0)}
                className="absolute right-3 top-1/2 inline-flex -translate-y-1/2 items-center justify-center rounded-[12px] bg-[#8ff5ff] px-5 py-2.5 text-[12px] font-bold uppercase tracking-[0.18em] text-[#005d63] shadow-[0px_10px_15px_-3px_rgba(143,245,255,0.2),0px_4px_6px_-4px_rgba(143,245,255,0.2)] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-600"
              >
                {streamSessionState.loading ? <Loader2 className="animate-spin" size={16} /> : 'Send'}
              </button>
            </div>
          </form>
        </div>
      </section>

      <aside
        ref={actionSpaceRef}
        className="hidden w-[372px] shrink-0 border-l border-[rgba(255,255,255,0.05)] bg-[rgba(12,14,20,0.78)] px-6 py-6 backdrop-blur-xl xl:flex xl:flex-col xl:overflow-y-auto"
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

          <div className="border-t border-[rgba(255,255,255,0.06)] pt-4">
            <button
              onClick={() => setActionSpaceState(prev => ({ ...prev, showDebug: !prev.showDebug }))}
              className="flex w-full items-center justify-between px-1 py-2 text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(170,170,179,0.76)] transition hover:text-[#e7e7f0]"
            >
              <span className="flex items-center gap-2">
                <Terminal size={14} className="text-[#8ff5ff]" />
                Raw Events ({actionSpaceState.rawTraces.length})
              </span>
              <ChevronDown size={14} className={cn('transition-transform duration-300', actionSpaceState.showDebug ? 'rotate-180' : '')} />
            </button>

            {actionSpaceState.showDebug ? (
              <div className="mt-3 max-h-96 space-y-2 overflow-y-auto rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.24)] p-3 font-mono text-[9px] text-[rgba(170,170,179,0.84)]">
                {actionSpaceState.rawTraces.length === 0 ? (
                  <div className="py-4 text-center italic text-[rgba(170,170,179,0.58)]">
                    No events recorded yet.
                  </div>
                ) : (
                  [...actionSpaceState.rawTraces].reverse().map((trace, i) => (
                    <div key={i} className="border-b border-[rgba(255,255,255,0.05)] pb-2 last:border-0 last:pb-0">
                      <div className="mb-1 flex items-center justify-between">
                        <span className={cn(
                          'rounded px-1.5 py-0.5 text-[8px] font-bold uppercase',
                          trace.event_type === 'error' ? 'bg-red-500/20 text-red-300' :
                          trace.event_type === 'status' ? 'bg-blue-500/20 text-blue-300' :
                          trace.event_type === 'tool_start' ? 'bg-emerald-500/20 text-emerald-300' :
                          'bg-[rgba(255,255,255,0.06)] text-[rgba(170,170,179,0.9)]'
                        )}>
                          {trace.event_type}
                        </span>
                        <span className="opacity-50">
                          {new Date(trace.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                      </div>
                      <pre className="whitespace-pre-wrap break-all opacity-85">
                        {JSON.stringify({ ...trace, timestamp: undefined, event_type: undefined }, (key, value) =>
                          typeof value === 'string' && value.length > 100 ? `${value.substring(0, 100)}...` : value
                        , 1)}
                      </pre>
                    </div>
                  ))
                )}
              </div>
            ) : null}
          </div>
        </div>
      </aside>
      </div>
    </main>
  );
}

export default function ChatWorkspacePage() {
  const router = useRouter();
  const { user, loading, refreshUser, updateUser, logout } = useAuth();

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

  return <WorkspaceApp currentUser={user} onLogout={handleLogout} onUserUpdated={updateUser} />;
}
