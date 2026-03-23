"use client";

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Send, Terminal, Loader2, Bot, User, Activity, Image as ImageIcon, X, ChevronDown, Menu } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import NextImage from 'next/image';
import { ChatMessage, StreamEvent, ToolExecution } from '@/types/agent';
import type { AuthUser } from '@/types/auth';
import type { ActionSpaceState, ActiveThreadState, StreamSessionState, ThreadCollectionState } from '@/types/thread';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { changePasswordUser, fetchThreadDetail, fetchThreads, patchThread, resumeChatStream, sendChatStream } from '@/lib/api';
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
  upsertThreadSummary,
} from '@/lib/workspace-state';
import { useAuth } from '@/components/auth/AuthProvider';
import { AdminStatusPanel } from '@/components/auth/AdminStatusPanel';
import { ProfilePanel } from '@/components/auth/ProfilePanel';
import { HITLPanel } from '@/components/HITLPanel';
import { AgentTimeline } from '@/components/sidebar/AgentTimeline';
import { SessionStatusCard } from '@/components/sidebar/SessionStatusCard';
import { ThreadListSidebar } from '@/components/sidebar/ThreadListSidebar';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
// --- Markdown Renderer ---
const MarkdownContent = ({ content }: { content: string }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
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

const ToolCard = ({ tool }: { tool: ToolExecution }) => {
  const [open, setOpen] = useState(false);
  const isRunning = tool.status === 'running';
  const duration = tool.endTime ? ((tool.endTime - tool.startTime) / 1000).toFixed(1) : null;

  return (
    <div className={cn(
      "backdrop-blur-lg bg-slate-900/40 p-4 rounded-2xl border transition-all duration-500 animate-in fade-in slide-in-from-right-4",
      isRunning ? "border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.2)]" : "border-slate-800/50"
    )}>
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="w-full text-left"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-2 h-2 rounded-full",
              isRunning ? "bg-blue-400 animate-pulse" : tool.status === 'success' ? "bg-emerald-400" : "bg-red-400"
            )} />
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400">Tool Call</span>
          </div>
          <div className="flex items-center gap-2">
            {duration && <span className="text-[10px] font-mono text-slate-500">{duration}s</span>}
            <ChevronDown
              size={14}
              className={cn("text-slate-500 transition-transform", open && "rotate-180")}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="p-2 bg-slate-800/50 rounded-lg text-blue-400">
            <Terminal size={14} />
          </div>
          <h4 className="text-sm font-bold text-slate-200">{tool.name}</h4>
        </div>
      </button>

      {open && (
        <>
          {!!tool.input && (
            <div className="mt-3 space-y-1">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Input</p>
              <pre className="text-[11px] bg-black/30 p-2 rounded-lg text-slate-400 overflow-x-auto font-mono max-h-24">
                {typeof tool.input === 'string' ? tool.input : JSON.stringify(tool.input, null, 2)}
              </pre>
            </div>
          )}

          {!!tool.output && (
            <div className="mt-3 space-y-1">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Output</p>
              <div className="text-[11px] bg-blue-500/5 border border-blue-500/10 p-2 rounded-lg text-slate-300 overflow-x-auto font-mono max-h-32">
                {typeof tool.output === 'string' ? tool.output : JSON.stringify(tool.output, null, 2)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const AgentThought = ({ content, isThinking }: { content: string, isThinking: boolean }) => {
  if (!content && !isThinking) return null;

  return (
    <div className="backdrop-blur-xl bg-blue-500/5 border border-blue-500/10 rounded-2xl p-4 mb-4 animate-in fade-in slide-in-from-top-2">
      <div className="flex items-center gap-2 mb-2">
        <Activity size={14} className="text-blue-400" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-blue-400">
          {isThinking ? "Internal Reasoning" : "Thought Summary"}
        </span>
      </div>
      <div className="text-xs text-slate-300 leading-relaxed font-mono whitespace-pre-wrap">
        {content}
        {isThinking && <span className="inline-block w-1.5 h-3 ml-1 bg-blue-400 animate-pulse" />}
      </div>
    </div>
  );
};

const ToolPanel = ({
  toolExecutions,
  emptyMessage = 'Waiting for tool execution...',
}: {
  toolExecutions: ToolExecution[];
  emptyMessage?: string;
}) => (
  <div className="flex flex-col gap-4">
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-semibold text-slate-400 flex items-center gap-2">
        <Terminal size={16} /> Tool Activity
      </h3>
      <span className="text-[10px] bg-slate-800 px-2 py-0.5 rounded text-slate-500 font-mono">
        {toolExecutions.length} calls
      </span>
    </div>
    <div className="flex flex-col gap-3">
      {toolExecutions.length === 0 ? (
        <div className="p-8 border border-dashed border-slate-800 rounded-2xl flex flex-col items-center justify-center text-center opacity-30">
          <Terminal size={24} className="mb-2" />
          <span className="text-xs italic tracking-tighter text-slate-400">{emptyMessage}</span>
        </div>
      ) : (
        [...toolExecutions].reverse().map((tool) => (
          <ToolCard key={tool.id} tool={tool} />
        ))
      )}
    </div>
  </div>
);

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
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-12 text-slate-100">
      <div className="w-full max-w-lg rounded-3xl border border-slate-800/80 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 backdrop-blur-xl">
        <div className="mb-8 flex items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Security Gate</div>
            <h1 className="mt-1 text-2xl font-bold text-slate-100">Change Your Password</h1>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              The bootstrap admin account is active as <span className="font-mono text-slate-200">{currentUser.login_id}</span>.
              You must replace the temporary password before using the workspace.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void onLogout()}
            className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-2 text-sm text-slate-300 transition hover:border-slate-700 hover:text-slate-100"
          >
            Log Out
          </button>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="current-password">
              Current Password
            </label>
            <input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Enter the current password"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="new-password">
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Create a new password"
              disabled={submitting}
            />
            <p className="mt-2 text-xs italic leading-5 text-slate-500">
              Password must be at least 15 characters and include lowercase letters and numbers.
            </p>
          </div>

          {error ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !currentPassword || !newPassword}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            <span>Change Password</span>
          </button>
        </form>
      </div>
    </main>
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
  const [threadCollectionState, setThreadCollectionState] = useState<ThreadCollectionState>(() => createInitialThreadCollectionState());
  const [activeThreadState, setActiveThreadState] = useState<ActiveThreadState>(() => createInitialActiveThreadState());
  const [streamSessionState, setStreamSessionState] = useState<StreamSessionState>(() => createInitialStreamSessionState());
  const [actionSpaceState, setActionSpaceState] = useState<ActionSpaceState>(() => createInitialActionSpaceState());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toolIdCounterRef = useRef(0);

  const scrollRef = useRef<HTMLDivElement>(null);
  const actionSpaceRef = useRef<HTMLDivElement>(null);
  const isInteractionLocked =
    streamSessionState.loading ||
    streamSessionState.isInterrupted ||
    activeThreadState.detailLoadState === 'loading';
  const isHistoricalView = activeThreadState.viewMode === 'historical';

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
    setMobileSidebarOpen(false);
  };

  const handleRenameThread = async (threadId: string, title: string) => {
    const existingThread = threadCollectionState.threads.find((thread) => thread.thread_id === threadId);
    if (!existingThread) {
      return;
    }

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
        threads: upsertThreadSummary(prev.threads, updatedThread),
      }));
      if (activeThreadState.threadId === threadId) {
        setActiveThreadState((prev) => applyThreadSummaryToActiveThread(prev, updatedThread));
      }
    } catch (error) {
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: upsertThreadSummary(prev.threads, existingThread),
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
        threads: upsertThreadSummary(prev.threads, updatedThread),
      }));
      if (activeThreadState.threadId === threadId) {
        setActiveThreadState((prev) => applyThreadSummaryToActiveThread(prev, updatedThread));
      }
    } catch (error) {
      setThreadCollectionState((prev) => ({
        ...prev,
        threads: upsertThreadSummary(prev.threads, existingThread),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
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

    try {
      const detail = await fetchThreadDetail(threadId);
      setActiveThreadState(createActiveThreadStateFromDetail(detail));
      setStreamSessionState(createHistoricalStreamSessionState(detail.thread.latest_status));
      setActionSpaceState(createInitialActionSpaceState());
      setThreadCollectionState(prev => ({
        ...prev,
        threads: upsertThreadSummary(prev.threads, detail.thread),
        error: '',
      }));
      setInput('');
      setSelectedImages([]);
      setMobileSidebarOpen(false);
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

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      const assistantMsgId = Date.now().toString() + "_ai";
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const { blocks, remainder } = splitSseBlocks(buffer);
        buffer = remainder;

        for (const block of blocks) {
          const payload = parseSseBlock(block) as StreamEvent | null;
          if (payload) {
            handleStreamEvent(payload, assistantMsgId, thread_id);
          }
        }

        if (done) {
          if (buffer.trim()) {
            const finalPayload = parseSseBlock(buffer) as StreamEvent | null;
            if (finalPayload) {
              handleStreamEvent(finalPayload, assistantMsgId, thread_id);
            }
          }
          setStreamSessionState(prev => ({
            ...prev,
            loading: false,
          }));
          await refreshThreadsSilently();
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

      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

        const { blocks, remainder } = splitSseBlocks(buffer);
        buffer = remainder;

        for (const block of blocks) {
          const payload = parseSseBlock(block) as StreamEvent | null;
          if (payload) {
            receivedStreamEvent = true;
            handleStreamEvent(payload, assistantMsgId, activeThreadState.threadId);
          }
        }

        if (done) {
          if (buffer.trim()) {
            const finalPayload = parseSseBlock(buffer) as StreamEvent | null;
            if (finalPayload) {
              receivedStreamEvent = true;
              handleStreamEvent(finalPayload, assistantMsgId, activeThreadState.threadId);
            }
          }
          setStreamSessionState(prev => ({
            ...prev,
            loading: false,
          }));
          await refreshThreadsSilently();
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

  const sidebarContent = (
    <>
      <div className="flex flex-col gap-4">
        <AgentTimeline
          history={streamSessionState.history}
          currentNode={streamSessionState.currentNode}
          loading={streamSessionState.loading}
          historicalView={isHistoricalView}
        />

        <SessionStatusCard
          loading={streamSessionState.loading}
          checkpointId={activeThreadState.checkpointId}
          activeThreadId={activeThreadState.threadId}
          threadCount={threadCollectionState.threads.length}
          threadLoadState={threadCollectionState.loadState}
          latestStatus={activeThreadState.latestStatus}
          lastActivityAt={activeThreadState.lastActivityAt}
          historicalView={isHistoricalView}
        />
      </div>

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
      />
    </>
  );

  return (
    <main className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans relative">
      {/* Decorative Background Elements */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/10 blur-[120px] rounded-full pointer-events-none" />

      {/* Left Sidebar: Session Info & History */}
      <aside className="hidden lg:flex lg:w-80 flex-col gap-4 border-r border-slate-800/50 bg-slate-950/50 p-4 backdrop-blur-xl z-10">
        <div className="flex items-center gap-3 mb-4 justify-center lg:justify-start">
          <div className="p-2 bg-blue-600 rounded-lg shadow-lg shadow-blue-500/20">
            <Bot className="text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-200">OrchAgent</h1>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          {sidebarContent}
        </div>
      </aside>

      {mobileSidebarOpen ? (
        <div className="fixed inset-0 z-30 lg:hidden">
          <button
            type="button"
            aria-label="Close thread sidebar"
            onClick={() => setMobileSidebarOpen(false)}
            className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm"
          />

          <div className="absolute inset-y-0 left-0 flex w-[min(24rem,92vw)] flex-col border-r border-slate-800/70 bg-slate-950/95 p-4 shadow-2xl shadow-black/50">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-blue-600 p-2 shadow-lg shadow-blue-500/20">
                  <Bot className="text-white" />
                </div>
                <h1 className="text-lg font-bold tracking-tight text-slate-200">OrchAgent</h1>
              </div>

              <button
                type="button"
                onClick={() => setMobileSidebarOpen(false)}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-2 text-slate-400 transition-colors hover:border-slate-700 hover:text-slate-200"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
              {sidebarContent}
            </div>
          </div>
        </div>
      ) : null}

      {/* Center Content: Chat Workspace */}
      <section className="flex-1 flex flex-col relative z-10 bg-transparent">
        <header className="flex h-16 items-center justify-between border-b border-slate-800/50 bg-slate-950/20 px-8 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-sm font-medium text-slate-400">
            <button
              type="button"
              onClick={() => setMobileSidebarOpen(true)}
              className="inline-flex rounded-xl border border-slate-800 bg-slate-900/60 p-2 text-slate-400 transition-colors hover:border-slate-700 hover:text-slate-200 lg:hidden"
            >
              <Menu size={16} />
            </button>
            <span>Thread</span>
            <span className="text-slate-600">/</span>
            <span className="hidden text-slate-300 sm:inline">
              {activeThreadState.title || 'New Chat'}
            </span>
            <span className="hidden text-slate-600 sm:inline">/</span>
            <span className="text-blue-400 font-mono text-xs bg-blue-400/10 px-2 py-0.5 rounded border border-blue-400/20">
              {activeThreadState.threadId || 'draft_session'}
            </span>
          </div>

          <div className="hidden items-center gap-3 sm:flex">
            <div className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-xs text-slate-400">
              <span className="mr-2 uppercase tracking-[0.2em] text-slate-500">User</span>
              <span className="font-mono text-slate-200">{currentUser.login_id}</span>
            </div>
            <button
              type="button"
              onClick={() => void onLogout()}
              className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-700 hover:text-slate-100"
            >
              Log Out
            </button>
          </div>
        </header>

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-8 space-y-6 scrollbar-thin scrollbar-thumb-slate-800"
        >
          {activeThreadState.detailLoadState === 'loading' && (
            <div className="flex h-full min-h-[16rem] items-center justify-center">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-6 py-5 text-sm text-slate-300 shadow-xl">
                <div className="flex items-center gap-3">
                  <Loader2 size={18} className="animate-spin text-blue-400" />
                  <span>Loading thread history...</span>
                </div>
              </div>
            </div>
          )}

          {activeThreadState.detailLoadState !== 'loading' && activeThreadState.messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto opacity-50">
              <div className="w-20 h-20 bg-slate-900 border border-slate-800 rounded-3xl flex items-center justify-center mb-6 shadow-xl">
                <Bot size={40} className="text-slate-400" />
              </div>
              <h2 className="text-2xl font-bold mb-2 text-slate-200">System Ready</h2>
              <p className="text-slate-400 text-sm">
                Initiate a hierarchical task. The multi-agent team is standing by for coordination.
              </p>
            </div>
          )}

          {activeThreadState.detailLoadState !== 'loading' && activeThreadState.messages.map((m) => (
            <div key={m.id} className={cn(
              "flex gap-4 max-w-3xl animate-in fade-in slide-in-from-bottom-2 duration-300",
              m.role === 'user' ? "ml-auto flex-row-reverse" : ""
            )}>
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm",
                m.role === 'user' ? "bg-slate-700" : "bg-blue-600"
              )}>
                {m.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </div>
              <div className={cn(
                "p-4 rounded-2xl leading-relaxed text-sm shadow-sm",
                m.role === 'user'
                  ? "bg-blue-600/10 border border-blue-500/20 text-slate-100"
                  : "bg-slate-900/80 border border-slate-800 text-slate-200 backdrop-blur-md"
              )}>
                {m.role === 'user' ? m.content : <MarkdownContent content={m.content} />}
              </div>            </div>
          ))}

          {streamSessionState.loading && (
            <div className="flex gap-4 max-w-3xl animate-pulse">
              <div className="w-8 h-8 rounded-full bg-blue-600/50 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="p-4 rounded-2xl bg-slate-900/50 border border-slate-800 text-slate-400 text-sm italic">
                {streamSessionState.currentNode || 'Coordinating team...'}
              </div>
            </div>
          )}

          {streamSessionState.isInterrupted && (
            <div className="flex gap-4 max-w-3xl">
              <div className="w-8 h-8 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="w-full">
                <HITLPanel onAction={handleResume} loading={streamSessionState.loading} />
              </div>
            </div>
          )}

          {!!streamSessionState.streamError && !streamSessionState.loading && (
            <div className="flex gap-4 max-w-3xl">
              <div className="w-8 h-8 rounded-full bg-red-500/20 text-red-300 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-200 text-sm">
                {streamSessionState.streamError}
              </div>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="p-8 pt-0">
          <form
            onSubmit={handleSubmit}
            className="max-w-3xl mx-auto relative group"
          >
            {/* Image Previews */}
            {selectedImages.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2 p-2 bg-slate-900/50 border border-slate-800/50 rounded-xl backdrop-blur-md">
                {selectedImages.map((file, i) => (
                  <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-700">
                    <NextImage
                      src={URL.createObjectURL(file)}
                      alt="preview"
                      width={64}
                      height={64}
                      className="w-full h-full object-cover"
                      unoptimized
                    />
                    <button
                      type="button"
                      onClick={() => removeImage(i)}
                      className="absolute top-0.5 right-0.5 p-0.5 bg-slate-950/80 text-white rounded-full hover:bg-red-500 transition-colors"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="relative">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Message OrchAgent..."
                className="w-full bg-slate-900/50 border border-slate-800/50 rounded-2xl py-4 pl-14 pr-14 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-600/30 transition-all placeholder:text-slate-600 backdrop-blur-md"
                disabled={isInteractionLocked}
              />
              <button
                type="button"
                aria-label="Attach image"
                onClick={() => fileInputRef.current?.click()}
                disabled={isInteractionLocked}
                className="absolute left-3 top-1/2 -translate-y-1/2 p-2 text-slate-500 hover:text-blue-400 disabled:text-slate-800 transition-colors"
              >
                <ImageIcon size={20} />
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
                className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl transition-colors shadow-lg shadow-blue-600/20"
              >
                {streamSessionState.loading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* Right Sidebar: Agent Action Space (Action Space) */}
      <aside
        ref={actionSpaceRef}
        className="hidden xl:flex w-96 border-l border-slate-800/50 bg-slate-950/30 backdrop-blur-2xl flex-col p-6 overflow-y-auto z-10 scrollbar-none"
      >
        <div className="flex items-center gap-2 mb-6">
          <Terminal size={18} className="text-blue-400" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">Action Space</h2>
        </div>

        <div className="space-y-6">
          <ProfilePanel user={currentUser} onUserUpdated={onUserUpdated} />
          {currentUser.role === 'admin' ? <AdminStatusPanel /> : null}

          {isHistoricalView ? (
            <div className="rounded-2xl border border-amber-500/20 bg-amber-500/8 px-4 py-4 text-sm text-amber-100/90">
              Historical thread selected. Tool activity, reasoning, and raw events are not hydrated in v1.
            </div>
          ) : null}

          <AgentThought content={actionSpaceState.reasoning} isThinking={streamSessionState.loading} />

          <ToolPanel
            toolExecutions={actionSpaceState.toolExecutions}
            emptyMessage={
              isHistoricalView
                ? 'Historical tool activity is not restored in v1.'
                : 'Waiting for tool execution...'
            }
          />

          {/* Debug Panel Toggle */}
          <div className="mt-8 border-t border-slate-800/30 pt-4">
            <button
              onClick={() => setActionSpaceState(prev => ({ ...prev, showDebug: !prev.showDebug }))}
              className="flex items-center justify-between w-full px-2 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors group"
            >
              <span className="flex items-center gap-2">
                <Terminal size={14} className="group-hover:text-blue-400" />
                Raw Events ({actionSpaceState.rawTraces.length})
              </span>
              <ChevronDown size={14} className={cn("transition-transform duration-300", actionSpaceState.showDebug ? "rotate-180" : "")} />
            </button>

            {actionSpaceState.showDebug && (
              <div className="mt-3 bg-black/40 rounded-xl border border-slate-800/50 p-3 max-h-96 overflow-y-auto font-mono text-[9px] text-slate-400 space-y-2 scrollbar-none animate-in fade-in slide-in-from-top-2">
                {actionSpaceState.rawTraces.length === 0 ? (
                  <div className="text-center py-4 text-slate-600 italic">No events recorded yet.</div>
                ) : (
                  [...actionSpaceState.rawTraces].reverse().map((trace, i) => (
                    <div key={i} className="border-b border-slate-800/30 pb-2 last:border-0 last:pb-0">
                      <div className="flex justify-between items-center mb-1">
                        <span className={cn(
                          "px-1.5 py-0.5 rounded uppercase font-bold text-[8px]",
                          trace.event_type === 'error' ? "bg-red-500/20 text-red-400" :
                          trace.event_type === 'status' ? "bg-blue-500/20 text-blue-400" :
                          trace.event_type === 'tool_start' ? "bg-emerald-500/20 text-emerald-400" :
                          "bg-slate-800 text-slate-400"
                        )}>
                          {trace.event_type}
                        </span>
                        <span className="text-[8px] opacity-50">{new Date(trace.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                      </div>
                      <pre className="whitespace-pre-wrap break-all opacity-80">
                        {JSON.stringify({ ...trace, timestamp: undefined, event_type: undefined }, (key, value) =>
                          typeof value === 'string' && value.length > 100 ? value.substring(0, 100) + '...' : value
                        , 1)}
                      </pre>
                    </div>
                  ))
                )}
              </div>
            )}
            <div className="mt-4 px-2">
              <p className="text-[11px] text-slate-500 italic leading-relaxed">
                Real-time tool execution logs and internal reasoning will be streamed here.
              </p>
            </div>
          </div>
        </div>
      </aside>    </main>
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
