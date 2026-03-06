export interface TraceEvent {
    event_type: string;
    node: string;
    data: unknown;
    timestamp: string;
}

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    id: string;
}

export interface AgentStatus {
    currentNode: string;
    runningTools: string[];
    history: string[];
}

export interface ToolExecution {
    id: string;
    name: string;
    status: 'pending' | 'running' | 'success' | 'error';
    input?: unknown;
    output?: unknown;
    startTime: number;
    endTime?: number;
}
