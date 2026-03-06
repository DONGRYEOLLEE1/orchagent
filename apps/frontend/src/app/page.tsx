"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Send, Terminal, Loader2, Bot, User, CheckCircle2, Activity, Image as ImageIcon, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import NextImage from 'next/image';
import { ChatMessage, ToolExecution } from '@/types/agent';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

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
  const isRunning = tool.status === 'running';
  const duration = tool.endTime ? ((tool.endTime - tool.startTime) / 1000).toFixed(1) : null;

  return (
    <div className={cn(
      "backdrop-blur-lg bg-slate-900/40 p-4 rounded-2xl border transition-all duration-500 animate-in fade-in slide-in-from-right-4",
      isRunning ? "border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.2)]" : "border-slate-800/50"
    )}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={cn(
            "w-2 h-2 rounded-full",
            isRunning ? "bg-blue-400 animate-pulse" : tool.status === 'success' ? "bg-emerald-400" : "bg-red-400"
          )} />
          <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400">Tool Call</span>
        </div>
        {duration && <span className="text-[10px] font-mono text-slate-500">{duration}s</span>}
      </div>

      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 bg-slate-800/50 rounded-lg text-blue-400">
          <Terminal size={14} />
        </div>
        <h4 className="text-sm font-bold text-slate-200">{tool.name}</h4>
      </div>

      {tool.input && (
        <div className="mt-2 space-y-1">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Input</p>
          <pre className="text-[11px] bg-black/30 p-2 rounded-lg text-slate-400 overflow-x-auto font-mono max-h-24">
            {typeof tool.input === 'string' ? tool.input : JSON.stringify(tool.input, null, 2)}
          </pre>
        </div>
      )}

      {tool.output && (
        <div className="mt-3 space-y-1">
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-tighter">Output</p>
          <div className="text-[11px] bg-blue-500/5 border border-blue-500/10 p-2 rounded-lg text-slate-300 overflow-x-auto font-mono max-h-32">
            {typeof tool.output === 'string' ? tool.output : JSON.stringify(tool.output, null, 2)}
          </div>
        </div>
      )}
    </div>
  );
};

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

const ToolPanel = ({ toolExecutions }: { toolExecutions: ToolExecution[] }) => (
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
          <span className="text-xs italic tracking-tighter text-slate-400">Waiting for tool execution...</span>
        </div>
      ) : (
        [...toolExecutions].reverse().map((tool) => (
          <ToolCard key={tool.id} tool={tool} />
        ))
      )}
    </div>
  </div>
);

// --- Main Page ---

export default function ChatWorkspace() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [currentNode, setCurrentNode] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [toolExecutions, setToolExecutions] = useState<ToolExecution[]>([]);
  const [reasoning, setReasoning] = useState('');
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const actionSpaceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, currentNode, reasoning]);

  useEffect(() => {
    if (actionSpaceRef.current) {
      actionSpaceRef.current.scrollTop = actionSpaceRef.current.scrollHeight;
    }
  }, [toolExecutions, reasoning]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedImages(prev => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const removeImage = (index: number) => {
    setSelectedImages(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && selectedImages.length === 0) || loading) return;

    const thread_id = `thread_${Date.now()}`;
    const userMessage: ChatMessage = { role: 'user', content: input, id: Date.now().toString() };

    // Convert images to base64
    const base64Images = await Promise.all(selectedImages.map(fileToBase64));

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setSelectedImages([]);
    setLoading(true);
    setCurrentNode('');
    setHistory([]);
    setToolExecutions([]);
    setReasoning('');

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          thread_id,
          images: base64Images.length > 0 ? base64Images : undefined
        }),
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const assistantMsgId = Date.now().toString() + "_ai";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              const { event_type, node, data, content } = payload;

              if (event_type === 'on_chain_start' && node === 'OrchAgent') {
                setCurrentNode('Head Supervisor');
              } else if (event_type === 'on_node_start') {
                setCurrentNode(node);
                setHistory(prev => [...prev, node]);
              } else if (event_type === 'on_tool_start') {
                const newTool: ToolExecution = {
                  id: Math.random().toString(36).substr(2, 9),
                  name: node,
                  status: 'running',
                  input: data,
                  startTime: Date.now()
                };
                setToolExecutions(prev => [...prev, newTool]);
              } else if (event_type === 'on_tool_end') {
                setToolExecutions(prev => prev.map(t =>
                  t.name === node && t.status === 'running'
                    ? { ...t, status: 'success', output: data, endTime: Date.now() }
                    : t
                ));
              } else if (event_type === 'reasoning') {
                setReasoning(prev => prev + (content || ''));
              } else if (event_type === 'on_chat_model_stream') {
                // Parse chunk data string to object to get content
                const dataObj = typeof data === 'string' ? JSON.parse(data.replace(/'/g, '"')) : data;
                const textChunk = dataObj?.chunk?.content || '';

                if (textChunk) {
                  setMessages(prev => {
                    const lastMsg = prev[prev.length - 1];
                    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.id === assistantMsgId) {
                      return [...prev.slice(0, -1), { ...lastMsg, content: lastMsg.content + textChunk }];
                    } else {
                      return [...prev, { role: 'assistant', content: textChunk, id: assistantMsgId }];
                    }
                  });
                }
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
    <main className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans relative">
      {/* Decorative Background Elements */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/10 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/10 blur-[120px] rounded-full pointer-events-none" />

      {/* Left Sidebar: Session Info & History */}
      <aside className="w-20 lg:w-64 border-r border-slate-800/50 flex flex-col gap-4 p-4 shrink-0 bg-slate-950/50 backdrop-blur-xl z-10">
        <div className="flex items-center gap-3 mb-4 justify-center lg:justify-start">
          <div className="p-2 bg-blue-600 rounded-lg shadow-lg shadow-blue-500/20">
            <Bot className="text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight hidden lg:block text-slate-200">OrchAgent</h1>
        </div>

        <div className="hidden lg:flex flex-col gap-4">
          <AgentTimeline history={history} currentNode={currentNode} />

          <div className="p-4 bg-slate-900/30 border border-slate-800/50 rounded-xl">
            <p className="text-xs text-slate-500 mb-1 font-mono uppercase tracking-wider">Session Status</p>
            <div className="flex justify-between text-sm">
              <span className="text-slate-400">Engine:</span>
              <span className={cn(loading ? "text-blue-400 animate-pulse" : "text-emerald-400 font-medium")}>
                {loading ? "Active" : "Idle"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* Center Content: Chat Workspace */}
      <section className="flex-1 flex flex-col relative z-10 bg-transparent">
        <header className="h-16 border-b border-slate-800/50 flex items-center px-8 bg-slate-950/20 backdrop-blur-sm">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-400">
            <span>Thread</span>
            <span className="text-slate-600">/</span>
            <span className="text-blue-400 font-mono text-xs bg-blue-400/10 px-2 py-0.5 rounded border border-blue-400/20">
              current_session
            </span>
          </div>
        </header>

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-8 space-y-6 scrollbar-thin scrollbar-thumb-slate-800"
        >
          {messages.length === 0 && (
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
                m.role === 'user'
                  ? "bg-blue-600/10 border border-blue-500/20 text-slate-100"
                  : "bg-slate-900/80 border border-slate-800 text-slate-200 backdrop-blur-md"
              )}>
                {m.role === 'user' ? m.content : <MarkdownContent content={m.content} />}
              </div>            </div>
          ))}

          {loading && (
            <div className="flex gap-4 max-w-3xl animate-pulse">
              <div className="w-8 h-8 rounded-full bg-blue-600/50 flex items-center justify-center shrink-0">
                <Bot size={16} />
              </div>
              <div className="p-4 rounded-2xl bg-slate-900/50 border border-slate-800 text-slate-400 text-sm italic">
                Coordinating team...
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
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
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
                disabled={loading || (!input.trim() && selectedImages.length === 0)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white rounded-xl transition-colors shadow-lg shadow-blue-600/20"
              >
                {loading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* Right Sidebar: Agent Action Space (Action Space) */}
      <aside
        ref={actionSpaceRef}
        className="w-96 border-l border-slate-800/50 bg-slate-950/30 backdrop-blur-2xl flex flex-col p-6 overflow-y-auto z-10 scrollbar-none"
      >
        <div className="flex items-center gap-2 mb-6">
          <Terminal size={18} className="text-blue-400" />
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-300">Action Space</h2>
        </div>

        <div className="space-y-6">
          <AgentThought content={reasoning} isThinking={loading && !history.includes('Completed')} />

          <ToolPanel toolExecutions={toolExecutions} />

          <div className="flex flex-col gap-2 p-4 bg-blue-500/5 border border-blue-500/10 rounded-2xl">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={14} className="text-blue-400" />
              <span className="text-xs font-semibold text-blue-300 uppercase">Live Trace</span>
            </div>
            <p className="text-[11px] text-slate-500 italic leading-relaxed">
              Real-time tool execution logs and internal reasoning will be streamed here.
            </p>
          </div>
        </div>
      </aside>    </main>
  );
}
