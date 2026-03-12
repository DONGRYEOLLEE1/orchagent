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
    runId?: string;
    name: string;
    status: 'pending' | 'running' | 'success' | 'error';
    input?: unknown;
    output?: unknown;
    startTime: number;
    endTime?: number;
}

export type StreamStatus = 'running' | 'completed' | 'errored' | 'interrupted';

export interface StreamStatusEvent {
    event_type: 'status';
    status: StreamStatus;
    thread_id: string;
    node?: string | null;
    display_name?: string | null;
    active_team?: string | null;
    active_worker?: string | null;
    message?: string;
    timestamp: string;
}

export interface StreamRouteEvent {
    event_type: 'route';
    node?: string | null;
    layer?: string | null;
    source?: string | null;
    target?: string | null;
    team?: string | null;
    worker?: string | null;
    status?: string | null;
    display_name?: string | null;
    timestamp: string;
}

export interface StreamTextEvent {
    event_type: 'text' | 'reasoning';
    node?: string | null;
    display_name?: string | null;
    content: string;
    run_id?: string;
    timestamp: string;
}

export interface StreamToolEvent {
    event_type: 'tool_start' | 'tool_end' | 'tool_error';
    node?: string | null;
    tool_name?: string | null;
    display_name?: string | null;
    input?: unknown;
    output?: unknown;
    error?: unknown;
    run_id?: string;
    timestamp: string;
}

export interface StreamCheckpointEvent {
    event_type: 'checkpoint';
    thread_id: string;
    checkpoint_id?: string | null;
    checkpoint_ns?: string | null;
    created_at?: string | null;
    next_nodes?: string[];
    active_team?: string | null;
    active_worker?: string | null;
    streaming_status?: string | null;
    message_count?: number;
    route_history_length?: number;
    timestamp: string;
}

export interface StreamErrorEvent {
    event_type: 'error';
    node?: string | null;
    message: string;
    timestamp: string;
}

export type StreamEvent =
    | StreamStatusEvent
    | StreamRouteEvent
    | StreamTextEvent
    | StreamToolEvent
    | StreamCheckpointEvent
    | StreamErrorEvent;
