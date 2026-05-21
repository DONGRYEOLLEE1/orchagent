"use client";

import React, { useState, useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ChatAttachment, ChatMessage, StreamEvent } from '@/types/agent';
import type { AuthUser } from '@/types/auth';
import {
  bindRepository,
  bindRepositoryZip,
  deleteRepositoryBinding,
  deleteThread,
  fetchThreadDetail,
  fetchThreadTelemetry,
  generateAiThreadTitle,
  generateSuggestedQueries,
  materializeRepository,
  patchThread,
  resumeChatStream,
  sendChatStream,
  uploadChatAttachments,
} from '@/lib/api';
import { appendAssistantText, parseSseBlock, splitSseBlocks } from '@/lib/chat-stream';
import { reduceStreamEvent, type StreamReducerState } from '@/lib/sse-reducer';
import {
  applyThreadSummaryToActiveThread,
  createActiveThreadStateFromDetail,
  createHistoricalStreamSessionState,
  createInitialActionSpaceState,
  createInitialActiveThreadState,
  createOptimisticThreadSummary,
  patchThreadSummary,
  createInitialStreamSessionState,
  sortThreadSummaries,
  upsertThreadSummary,
} from '@/lib/workspace-state';
import { useThreadCollection } from '@/hooks/useThreadCollection';
import { useActiveThread } from '@/hooks/useActiveThread';
import { useStreamSession } from '@/hooks/useStreamSession';
import { useActionSpace } from '@/hooks/useActionSpace';
import { useAuth } from '@/components/auth/AuthProvider';
import { AgentTimeline } from '@/components/sidebar/AgentTimeline';
import { ReasoningSummaryPanel } from '@/components/workspace/ReasoningSummaryPanel';
import { SuggestedQueriesPanel } from '@/components/workspace/SuggestedQueriesPanel';
import { AccountDrawer } from '@/components/workspace/AccountDrawer';
import RepositoryBindingPanel from '@/components/workspace/RepositoryBindingPanel';
import {
  ExecutionPolicyCard,
  VerificationStatusCard,
  hasCodingSignal,
} from '@/components/workspace/CodingSummaryPanels';
import { CodingAsideTabs } from '@/components/workspace/CodingAsideTabs';
import { RepoTreePanel } from '@/components/workspace/RepoTreePanel';
import { WorkspaceTopNav } from '@/components/workspace/WorkspaceTopNav';
import { MessageThreadView } from '@/components/workspace/MessageThreadView';
import { ComposerPanel } from '@/components/workspace/ComposerPanel';
import { WorkspaceSidebar } from '@/components/workspace/WorkspaceSidebar';
import { AuthLoadingScreen } from '@/components/workspace/internal/AuthLoadingScreen';
import { MustChangePasswordView } from '@/components/workspace/internal/MustChangePasswordView';
import { ImageLightbox } from '@/components/workspace/internal/ImageLightbox';
import {
  buildOptimisticAttachments,
  summarizeUploadErrors,
  validateIncomingDraftFiles,
  type DraftAttachmentItem,
  type DraftAttachmentStatusMap,
} from '@/components/workspace/internal/attachment-utils';

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
  // Workspace state slices are owned by dedicated hooks (Phase 3.2). Each
  // hook returns its slice + a raw setState plus high-level actions; we keep
  // the raw setState aliases in scope so the merged-snapshot SSE reducer
  // (`handleStreamEvent` below) can fan out per-slice patches synchronously
  // through `reducerStateRef`.
  const threadCollection = useThreadCollection();
  const activeThread = useActiveThread();
  const streamSessionHook = useStreamSession();
  const actionSpaceHook = useActionSpace();

  const threadCollectionState = threadCollection.threadCollection;
  const setThreadCollectionState = threadCollection.setThreadCollection;
  const activeThreadState = activeThread.activeThread;
  const setActiveThreadState = activeThread.setActiveThread;
  const streamSessionState = streamSessionHook.streamSession;
  const setStreamSessionState = streamSessionHook.setStreamSession;
  const actionSpaceState = actionSpaceHook.actionSpace;
  const setActionSpaceState = actionSpaceHook.setActionSpace;
  const activeThreadIdRef = activeThread.activeThreadIdRef;
  const toolIdCounterRef = useRef(0);
  // Mirror of the four workspace slices + tool-id counter, kept in sync via
  // the effect below. The SSE reducer consumes this snapshot synchronously
  // so a burst of events within a single async tick sees the most recent
  // state (functional setStates alone cannot expose a merged 4-slice view).
  const reducerStateRef = useRef<StreamReducerState>({
    threadCollection: threadCollectionState,
    activeThread: activeThreadState,
    streamSession: streamSessionState,
    actionSpace: actionSpaceState,
    nextToolId: toolIdCounterRef.current,
  });
  const pendingTitleRequestIdsRef = useRef<Record<string, string>>({});
  const pendingTelemetryRequestIdsRef = useRef<Record<string, string>>({});
  const pendingSuggestionRequestIdsRef = useRef<Record<string, string>>({});
  // NOTE: activeThreadIdRef is now owned by useActiveThread() and aliased
  // above so the rest of this component continues to read it through the
  // same identifier.

  const scrollRef = useRef<HTMLDivElement>(null);
  const actionSpaceRef = useRef<HTMLDivElement>(null);
  const isInteractionLocked =
    streamSessionState.loading ||
    streamSessionState.isInterrupted;
  const isHistoricalView = activeThreadState.viewMode === 'historical';

  // Keep the reducer ref aligned with React state every time any slice
  // changes. Within a single event-loop tick, handleStreamEvent itself
  // also advances reducerStateRef.current synchronously after each event
  // so successive events in a burst observe the latest merged state.
  useEffect(() => {
    reducerStateRef.current = {
      threadCollection: threadCollectionState,
      activeThread: activeThreadState,
      streamSession: streamSessionState,
      actionSpace: actionSpaceState,
      nextToolId: reducerStateRef.current.nextToolId,
    };
  }, [
    threadCollectionState,
    activeThreadState,
    streamSessionState,
    actionSpaceState,
  ]);

  const lastAutoTabThreadRef = useRef<string | null>(null);
  useEffect(() => {
    const tid = activeThreadState.threadId;
    if (!tid) {
      lastAutoTabThreadRef.current = null;
      return;
    }
    if (activeThreadState.detailLoadState !== 'success') return;
    if (lastAutoTabThreadRef.current === tid) return;
    const hasCodingContext =
      !!activeThreadState.repoBinding || hasCodingSignal(activeThreadState.codingSummary);
    setActionSpaceState((prev) => ({
      ...prev,
      activeRightTab: hasCodingContext ? 'coding' : 'reasoning',
    }));
    lastAutoTabThreadRef.current = tid;
  }, [
    activeThreadState.threadId,
    activeThreadState.detailLoadState,
    activeThreadState.repoBinding,
    activeThreadState.codingSummary,
    setActionSpaceState,
  ]);

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

  // Initial thread list fetch is owned by useThreadCollection() (Phase 3.2).

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
    const threads = await threadCollection.refreshThreadsSilently();
    if (!threads) {
      return;
    }
    const summary = threads.find(
      (thread) => thread.thread_id === activeThread.activeThread.threadId
    );
    if (summary) {
      activeThread.applySummary(summary);
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
    // Pure reducer call: state in -> next state out, no side effects.
    const previous = reducerStateRef.current;
    const next = reduceStreamEvent(previous, payload, {
      assistantMsgId,
      threadId,
      now: Date.now(),
    });

    // Sync the snapshot synchronously so a burst of events within a single
    // tick (e.g. multiple SSE blocks parsed in one for-loop iteration) all
    // observe the latest merged state via reducerStateRef.current.
    reducerStateRef.current = next;
    toolIdCounterRef.current = next.nextToolId;

    // Fan out per-slice setStates — React batches these into one render.
    if (previous.threadCollection !== next.threadCollection) {
      setThreadCollectionState(next.threadCollection);
    }
    if (previous.activeThread !== next.activeThread) {
      setActiveThreadState(next.activeThread);
    }
    if (previous.streamSession !== next.streamSession) {
      setStreamSessionState(next.streamSession);
    }
    if (previous.actionSpace !== next.actionSpace) {
      setActionSpaceState(next.actionSpace);
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
        <WorkspaceSidebar
          threads={threadCollectionState.threads}
          loadState={threadCollectionState.loadState}
          error={threadCollectionState.error}
          activeThreadId={activeThreadState.threadId}
          disabled={isInteractionLocked}
          mobileSidebarOpen={mobileSidebarOpen}
          onCloseMobileSidebar={() => setMobileSidebarOpen(false)}
          onCreateThread={handleStartNewChat}
          onSelectThread={handleSelectThread}
          onRenameThread={handleRenameThread}
          onTogglePinnedThread={handleTogglePinnedThread}
          onDeleteThread={handleDeleteThread}
        />

        <section className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 md:px-8">
            <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8">
              <MessageThreadView
                messages={activeThreadState.messages}
                detailLoadState={activeThreadState.detailLoadState}
                toolExecutions={actionSpaceState.toolExecutions}
                isHistoricalView={isHistoricalView}
                loading={streamSessionState.loading}
                isInterrupted={streamSessionState.isInterrupted}
                streamError={streamSessionState.streamError}
                currentNode={streamSessionState.currentNode}
                onImageSelect={setLightboxAttachment}
                onResume={handleResume}
              />
            </div>
          </div>

          <ComposerPanel
            input={input}
            onInputChange={setInput}
            selectedFiles={selectedFiles}
            selectedFileStatuses={selectedFileStatuses}
            attachmentUploadState={attachmentUploadState}
            attachmentError={attachmentError}
            onAttachmentChange={handleAttachmentChange}
            onRemoveAttachment={removeSelectedFile}
            onSubmit={handleSubmit}
            isInteractionLocked={isInteractionLocked}
            loading={streamSessionState.loading}
            hasSendableAttachments={hasSendableAttachments}
            repoBinding={activeThreadState.repoBinding}
            repoBindingLoading={repoBindingLoading}
            repoBindingError={repoBindingError}
            onBindRepositoryUrl={handleBindRepositoryUrl}
            onBindRepositoryZip={handleBindRepositoryZip}
            onDeleteRepositoryBinding={handleDeleteRepositoryBinding}
            onMaterializeRepository={handleMaterializeRepository}
          />
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
            <CodingAsideTabs
              active={actionSpaceState.activeRightTab}
              codingCount={
                (activeThreadState.codingSummary?.changed_files?.length || 0)
                + (activeThreadState.codingSummary?.verification_results?.length || 0)
              }
              onChange={(next) =>
                setActionSpaceState(prev => ({ ...prev, activeRightTab: next }))
              }
            />

            {actionSpaceState.activeRightTab === 'reasoning' ? (
              <div
                id="aside-panel-reasoning"
                role="tabpanel"
                aria-labelledby="aside-tab-reasoning"
                className="space-y-6"
              >
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
            ) : (
              <div
                id="aside-panel-coding"
                role="tabpanel"
                aria-labelledby="aside-tab-coding"
                className="space-y-6"
              >
                {activeThreadState.repoBinding || hasCodingSignal(activeThreadState.codingSummary) ? (
                  <>
                    {activeThreadState.repoBinding ? (
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
                    ) : null}
                    <RepoTreePanel summary={activeThreadState.codingSummary} />
                    <VerificationStatusCard summary={activeThreadState.codingSummary} />
                    <ExecutionPolicyCard summary={activeThreadState.codingSummary} />
                  </>
                ) : (
                  <div className="rounded-[12px] border border-dashed border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.3)] px-4 py-3 text-[12px] leading-6 text-[rgba(170,170,179,0.78)]">
                    Bind a repository and send a coding request to see changed files, verification
                    results, and the execution policy of the run here.
                  </div>
                )}
              </div>
            )}
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
