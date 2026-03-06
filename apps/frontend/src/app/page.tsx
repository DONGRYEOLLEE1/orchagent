"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Send, Terminal, Loader2, Bot, User, CheckCircle2, ChevronRight, Activity } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Components ---

const AgentTimeline = ({ history, currentNode }: { history: string[], currentNode: string }) => (
  <div className="flex flex-col gap-2 p-4 bg-slate-900/50 border border-slate-800 rounded-lg overflow-y-auto max-h-[300px]">
    <h3 className="text-sm font-semibold text-slate-400 flex items-center gap-2">
      <Activity size={16} /> Agent Timeline
    </h3>
    <div className="flex flex-col gap-3">
      {history.map((node, i) => (
        <div key={i} className="flex items-center gap-3 text-sm text-slate-300">
          <CheckCircle2 size={14} className="text-emerald-500" />
          <span>{node}</span>
        </div>
      ))}
      {currentNode && (
        <div className="flex items-center gap-3 text-sm font-medium text-blue-400 animate-pulse">
          <Loader2 size={14} className="animate-spin" />
          <span>{currentNode} (Running...)</span>
        </div>
      )}
    </div>
  </div>
);

const ToolPanel = ({ runningTools }: { runningTools: string[] }) => (
  <div className="flex flex-col gap-2 p-4 bg-slate-900/50 border border-slate-800 rounded-lg">
    <h3 className="text-sm font-semibold text-slate-400 flex items-center gap-2">
      <Terminal size={16} /> Active Tools
    </h3>
    <div className="flex flex-wrap gap-2">
      {runningTools.length === 0 ? (
        <span className="text-xs text-slate-500 italic">No active tools</span>
      ) : (
        runningTools.map((tool, i) => (
          <span key={i} className="px-2 py-1 bg-blue-900/30 border border-blue-700/50 text-blue-300 rounded text-xs flex items-center gap-1">
            <Loader2 size={10} className="animate-spin" /> {tool}
          </span>
        ))
      )}
    </div>
  </div>
);

// --- Main Page ---

export default function ChatWorkspace() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentNode, setCurrentNode] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [runningTools, setRunningTools] = useState<string[]>([]);
  
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, currentNode]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const thread_id = `thread_${Date.now()}`;
    const userMessage = { role: 'user', content: input, id: Date.now().toString() };
    
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setCurrentNode('');
    setHistory([]);
    setRunningTools([]);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input, thread_id }),
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              const { event_type, node, data } = payload;

              // Update logic based on event types
              if (event_type === 'on_chain_start' && node === 'OrchAgent') {
                setCurrentNode('Head Supervisor');
              } else if (event_type === 'on_node_start') {
                setCurrentNode(node);
                setHistory(prev => [...prev, node]);
              } else if (event_type === 'on_tool_start') {
                setRunningTools(prev => [...prev, node]);
              } else if (event_type === 'on_tool_end') {
                setRunningTools(prev => prev.filter(t => t !== node));
              } else if (event_type === 'on_chat_model_stream') {
                // Final answer or partial output handling could go here
              } else if (event_type === 'on_chain_end' && node === 'OrchAgent') {
                setLoading(false);
                setCurrentNode('Completed');
              }
            } catch (e) {
              console.error("Failed to parse event", e);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  return (
    <main className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Left Sidebar: Timeline & Stats */}
      <aside className="w-80 border-r border-slate-800 flex flex-col gap-4 p-4 shrink-0">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-blue-600 rounded-lg shadow-lg shadow-blue-500/20">
            <Bot className="text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">OrchAgent</h1>
        </div>
        
        <AgentTimeline history={history} currentNode={currentNode} />
        <ToolPanel runningTools={runningTools} />
        
        <div className="mt-auto p-4 bg-slate-900/30 border border-slate-800 rounded-lg">
          <p className="text-xs text-slate-500 mb-1">Session Info</p>
          <div className="flex justify-between text-sm">
            <span>Status:</span>
            <span className={cn(loading ? "text-blue-400" : "text-emerald-400 font-medium")}>
              {loading ? "Running" : "Idle"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Content: Chat Area */}
      <section className="flex-1 flex flex-col relative">
        <div 
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-8 space-y-6"
        >
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto">
              <div className="w-20 h-20 bg-slate-900 border border-slate-800 rounded-3xl flex items-center justify-center mb-6 shadow-xl">
                <Bot size={40} className="text-blue-500" />
              </div>
              <h2 className="text-2xl font-bold mb-2">Welcome to OrchAgent</h2>
              <p className="text-slate-400">
                Ask me to research complex topics, write reports, or generate code. I'll coordinate a team of agents to get it done.
              </p>
            </div>
          )}
          
          {messages.map((m) => (
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
                m.role === 'user' ? "bg-slate-800 text-slate-100" : "bg-slate-900 border border-slate-800 text-slate-200"
              )}>
                {m.content}
              </div>
            </div>
          ))}
          
          {loading && (
            <div className="flex gap-4 max-w-3xl animate-pulse">
              <div className="w-8 h-8 rounded-full bg-blue-600/50 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 text-slate-400 text-sm">
                Thinking and coordinating...
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
            <input 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="How can I help you today?"
              className="w-full bg-slate-900 border border-slate-800 rounded-2xl py-4 pl-6 pr-14 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-600/50 transition-all placeholder:text-slate-600"
              disabled={loading}
            />
            <button 
              type="submit"
              disabled={loading || !input.trim()}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl transition-colors"
            >
              {loading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
            </button>
          </form>
          <p className="text-[10px] text-center text-slate-600 mt-4 uppercase tracking-widest font-semibold">
            OrchAgent • Hierarchical Multi-Agent Platform
          </p>
        </div>
      </section>
    </main>
  );
}
