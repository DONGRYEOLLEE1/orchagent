export interface TraceEvent {
    event_type: string;
    node: string;
    data: any;
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
