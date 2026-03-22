import type { ChatMessage, StreamEvent, ToolExecution } from '@/types/agent';

export interface ThreadSummary {
  thread_id: string;
  title: string;
  preview: string;
  created_at: string | null;
  last_activity_at: string | null;
  message_count: number;
  latest_status: string | null;
  checkpoint_id: string | null;
}

export interface ThreadMessage {
  id: string;
  role: ChatMessage['role'];
  content: string;
  created_at: string | null;
}

export interface ThreadDetail {
  thread: ThreadSummary;
  messages: ThreadMessage[];
}

export type ThreadLoadState = 'idle' | 'loading' | 'success' | 'error';

export interface ThreadCollectionState {
  threads: ThreadSummary[];
  loadState: ThreadLoadState;
  error: string;
}

export interface ActiveThreadState {
  threadId: string;
  checkpointId: string;
  messages: ChatMessage[];
}

export interface StreamSessionState {
  loading: boolean;
  currentNode: string;
  history: string[];
  streamError: string;
  isInterrupted: boolean;
}

export interface ActionSpaceState {
  toolExecutions: ToolExecution[];
  reasoning: string;
  rawTraces: StreamEvent[];
  showDebug: boolean;
}
