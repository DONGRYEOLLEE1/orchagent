import type { ChatMessage } from '@/types/agent';
import type {
  ActionSpaceState,
  ActiveThreadState,
  StreamSessionState,
  ThreadDetail,
  ThreadCollectionState,
  ThreadMessage,
  ThreadSummary,
} from '@/types/thread';

export function createInitialThreadCollectionState(): ThreadCollectionState {
  return {
    threads: [],
    loadState: 'idle',
    error: '',
  };
}

export function createInitialActiveThreadState(): ActiveThreadState {
  return {
    threadId: '',
    title: '',
    checkpointId: '',
    messages: [],
    repoBinding: null,
    codingSummary: null,
    detailLoadState: 'idle',
    latestStatus: null,
    lastActivityAt: null,
    viewMode: 'draft',
  };
}

export function createInitialStreamSessionState(): StreamSessionState {
  return {
    loading: false,
    currentNode: '',
    history: [],
    streamError: '',
    isInterrupted: false,
  };
}

export function createInitialActionSpaceState(): ActionSpaceState {
  return {
    toolExecutions: [],
    reasoning: '',
    reasoningEntries: [],
    suggestedQueries: [],
    suggestedQueriesState: 'idle',
    suggestedQueriesError: '',
    rawTraces: [],
    showDebug: false,
    activeRightTab: 'reasoning',
  };
}

export function toChatMessages(messages: ThreadMessage[]): ChatMessage[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    attachments: message.attachments || [],
  }));
}

function truncateText(content: string, limit: number): string {
  const collapsed = content.trim().replace(/\s+/g, ' ');
  if (collapsed.length <= limit) {
    return collapsed;
  }

  return `${collapsed.slice(0, Math.max(limit - 3, 1)).trimEnd()}...`;
}

function toSortableTimestamp(value: string | null): number {
  if (!value) {
    return 0;
  }

  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

export function sortThreadSummaries(threads: ThreadSummary[]): ThreadSummary[] {
  return [...threads].sort((left, right) => {
    if (left.pinned !== right.pinned) {
      return left.pinned ? -1 : 1;
    }

    const leftLastActivity = toSortableTimestamp(left.last_activity_at || left.created_at);
    const rightLastActivity = toSortableTimestamp(right.last_activity_at || right.created_at);
    if (leftLastActivity !== rightLastActivity) {
      return rightLastActivity - leftLastActivity;
    }

    const leftCreatedAt = toSortableTimestamp(left.created_at);
    const rightCreatedAt = toSortableTimestamp(right.created_at);
    return rightCreatedAt - leftCreatedAt;
  });
}

export function createOptimisticThreadSummary(params: {
  threadId: string;
  content: string;
  existingThread?: ThreadSummary;
}): ThreadSummary {
  const { threadId, content, existingThread } = params;
  const timestamp = new Date().toISOString();
  const title = existingThread?.title || truncateText(content, 80) || 'Untitled chat';
  const preview = truncateText(content, 140);

  return {
    thread_id: threadId,
    title,
    preview,
    created_at: existingThread?.created_at || timestamp,
    last_activity_at: timestamp,
    message_count: existingThread ? existingThread.message_count + 1 : 1,
    latest_status: 'running',
    checkpoint_id: existingThread?.checkpoint_id || null,
    pinned: existingThread?.pinned || false,
    archived: existingThread?.archived || false,
  };
}

export function upsertThreadSummary(
  threads: ThreadSummary[],
  summary: ThreadSummary
): ThreadSummary[] {
  return sortThreadSummaries([
    summary,
    ...threads.filter((thread) => thread.thread_id !== summary.thread_id),
  ]);
}

export function patchThreadSummary(
  threads: ThreadSummary[],
  threadId: string,
  patch: Partial<ThreadSummary>
): ThreadSummary[] {
  return sortThreadSummaries(
    threads.map((thread) =>
      thread.thread_id === threadId ? { ...thread, ...patch } : thread
    )
  );
}

export function createActiveThreadStateFromDetail(
  detail: ThreadDetail
): ActiveThreadState {
  return {
    threadId: detail.thread.thread_id,
    title: detail.thread.title,
    checkpointId: detail.thread.checkpoint_id || '',
    messages: toChatMessages(detail.messages),
    repoBinding: detail.repository_binding || null,
    codingSummary: detail.coding_summary || null,
    detailLoadState: 'success',
    latestStatus: detail.thread.latest_status,
    lastActivityAt: detail.thread.last_activity_at,
    viewMode: 'historical',
  };
}

export function applyThreadSummaryToActiveThread(
  activeThread: ActiveThreadState,
  summary: ThreadSummary
): ActiveThreadState {
  return {
    ...activeThread,
    title: summary.title,
    checkpointId: summary.checkpoint_id || activeThread.checkpointId,
    latestStatus: summary.latest_status,
    lastActivityAt: summary.last_activity_at,
  };
}

export function createHistoricalStreamSessionState(
  latestStatus: string | null
): StreamSessionState {
  const baseState = createInitialStreamSessionState();

  if (latestStatus === 'interrupted') {
    return {
      ...baseState,
      currentNode: 'Requires User Action',
      isInterrupted: true,
    };
  }

  if (latestStatus === 'completed') {
    return {
      ...baseState,
      currentNode: 'Completed',
    };
  }

  if (latestStatus === 'errored') {
    return {
      ...baseState,
      currentNode: 'Errored',
    };
  }

  if (latestStatus === 'running') {
    return {
      ...baseState,
      currentNode: 'In Progress',
    };
  }

  return baseState;
}
