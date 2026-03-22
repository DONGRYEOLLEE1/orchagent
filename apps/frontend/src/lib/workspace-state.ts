import type { ChatMessage } from '@/types/agent';
import type {
  ActionSpaceState,
  ActiveThreadState,
  StreamSessionState,
  ThreadCollectionState,
  ThreadMessage,
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
    checkpointId: '',
    messages: [],
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
    rawTraces: [],
    showDebug: false,
  };
}

export function toChatMessages(messages: ThreadMessage[]): ChatMessage[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
  }));
}
