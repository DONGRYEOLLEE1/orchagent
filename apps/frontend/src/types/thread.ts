import type { ChatMessage, StreamEvent, ToolExecution } from '@/types/agent';

export interface ThreadAttachment {
  kind: 'image' | 'pdf' | 'spreadsheet' | 'csv' | 'json' | 'docx' | 'artifact';
  url: string;
  alt: string;
  file_name?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  preview: string;
  created_at: string | null;
  last_activity_at: string | null;
  message_count: number;
  latest_status: string | null;
  checkpoint_id: string | null;
  pinned: boolean;
  archived: boolean;
}

export interface ThreadMessage {
  id: string;
  role: ChatMessage['role'];
  content: string;
  created_at: string | null;
  attachments?: ThreadAttachment[];
}

export interface ThreadDetail {
  thread: ThreadSummary;
  messages: ThreadMessage[];
}

export interface ThreadTelemetry {
  thread_id: string;
  reasoning_summary: string;
  suggested_queries: string[];
}

export type ThreadLoadState = 'idle' | 'loading' | 'success' | 'error';
export type ActiveThreadViewMode = 'draft' | 'live' | 'historical';

export interface ThreadCollectionState {
  threads: ThreadSummary[];
  loadState: ThreadLoadState;
  error: string;
}

export interface ActiveThreadState {
  threadId: string;
  title: string;
  checkpointId: string;
  messages: ChatMessage[];
  detailLoadState: ThreadLoadState;
  latestStatus: string | null;
  lastActivityAt: string | null;
  viewMode: ActiveThreadViewMode;
}

export interface StreamSessionState {
  loading: boolean;
  currentNode: string;
  history: string[];
  streamError: string;
  isInterrupted: boolean;
}

export interface ReasoningEntry {
  id: string;
  node?: string | null;
  displayName?: string | null;
  content: string;
  timestamp?: string;
  runId?: string;
}

export interface ActionSpaceState {
  toolExecutions: ToolExecution[];
  reasoning: string;
  reasoningEntries: ReasoningEntry[];
  suggestedQueries: string[];
  suggestedQueriesState: 'idle' | 'loading' | 'success' | 'error';
  suggestedQueriesError: string;
  rawTraces: StreamEvent[];
  showDebug: boolean;
}
