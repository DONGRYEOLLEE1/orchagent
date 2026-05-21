"use client";

import React from 'react';
import { Bot, Loader2 } from 'lucide-react';

import { cn } from '@/lib/cn';
import { ChatAttachment, ChatMessage, ToolExecution } from '@/types/agent';
import type { ThreadLoadState } from '@/types/thread';

import { HITLPanel } from '@/components/HITLPanel';
import { LiveToolStatusStrip } from '@/components/workspace/LiveToolStatusStrip';
import { MarkdownContent } from '@/components/workspace/internal/MarkdownContent';
import { MessageAttachmentStrip } from '@/components/workspace/internal/MessageAttachmentStrip';

export interface MessageThreadViewProps {
  /** Ordered chat messages currently rendered in the thread. */
  messages: ChatMessage[];
  /** Persisted hydration state for the active thread (drives the loading panel). */
  detailLoadState: ThreadLoadState;
  /** Live tool executions surfaced under the latest assistant turn. */
  toolExecutions: ToolExecution[];
  /** Whether the active thread is in historical view (no live overlays). */
  isHistoricalView: boolean;
  /** Whether an SSE stream is currently in-flight. */
  loading: boolean;
  /** Whether the workflow is currently paused awaiting HITL input. */
  isInterrupted: boolean;
  /** Latest stream error (rendered as a banner once loading stops). */
  streamError: string;
  /** Active graph node label surfaced while loading / interrupted. */
  currentNode: string;
  /** Callback invoked when an image attachment is opened in the lightbox. */
  onImageSelect: (attachment: ChatAttachment) => void;
  /** Resume handler wired to the HITL panel. */
  onResume: (action: string, feedback: string) => void | Promise<void>;
}

/**
 * Pure presentation slice of WorkspaceRouteRoot: maps over `messages`, renders
 * attachment strips, live tool status, HITL panel and stream-error banner.
 *
 * State stays in WorkspaceApp; this component only consumes props and emits
 * `onImageSelect` / `onResume` callbacks.
 */
export function MessageThreadView({
  messages,
  detailLoadState,
  toolExecutions,
  isHistoricalView,
  loading,
  isInterrupted,
  streamError,
  currentNode,
  onImageSelect,
  onResume,
}: MessageThreadViewProps) {
  const latestThreadMessage = messages[messages.length - 1];
  const latestAssistantMessageId =
    latestThreadMessage?.role === 'assistant' ? latestThreadMessage.id : undefined;

  const shouldShowStandaloneToolStrip =
    loading &&
    !isHistoricalView &&
    !latestAssistantMessageId &&
    (toolExecutions.length > 0 || Boolean(currentNode));

  return (
    <>
      {detailLoadState === 'loading' ? (
        <div className="flex min-h-[16rem] items-center justify-center">
          <div className="rounded-[16px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.5)] px-6 py-5 text-sm text-[rgba(231,231,240,0.88)] shadow-xl">
            <div className="flex items-center gap-3">
              <Loader2 size={18} className="animate-spin text-[#8ff5ff]" />
              <span>Loading thread history...</span>
            </div>
          </div>
        </div>
      ) : null}

      {detailLoadState !== 'loading' && messages.length === 0 ? (
        <div className="mx-auto flex min-h-[26rem] max-w-md flex-col items-center justify-center text-center">
          <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-[20px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.5)] shadow-xl">
            <Bot size={36} className="text-[#8ff5ff]" />
          </div>
          <h2 className="font-[var(--font-display)] text-[28px] font-bold text-[#e7e7f0]">
            System Ready
          </h2>
          <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.78)]">
            Initiate a hierarchical task. The orchestration workspace will reveal reasoning summaries, tool activity, and follow-up prompts in context.
          </p>
        </div>
      ) : null}

      {detailLoadState !== 'loading'
        ? messages.map((message) => {
            const isUser = message.role === 'user';
            const showToolStatuses =
              !isUser &&
              !isHistoricalView &&
              message.id === latestAssistantMessageId &&
              toolExecutions.length > 0;

            return (
              <div
                key={message.id}
                className={cn(
                  'animate-in fade-in slide-in-from-bottom-2 duration-300',
                  isUser ? 'ml-auto flex w-full justify-end' : 'flex w-full justify-start'
                )}
              >
                {isUser ? (
                  <div className="flex w-full max-w-[520px] flex-col items-end">
                    <MessageAttachmentStrip
                      attachments={message.attachments || []}
                      align="end"
                      onImageSelect={onImageSelect}
                    />
                    {message.content.trim() ? (
                      <div className="rounded-bl-[14px] rounded-br-[14px] rounded-tl-[14px] border border-[rgba(143,245,255,0.14)] bg-[rgba(35,38,46,0.28)] px-4 py-3 text-[13px] leading-6 text-[#e7e7f0] backdrop-blur-[12px]">
                        {message.content}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="flex w-full max-w-[680px] items-start gap-4">
                    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[#7000ff] text-white shadow-[0px_0px_0px_2px_rgba(172,137,255,0.2)]">
                      <Bot size={14} />
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-3">
                      {showToolStatuses ? (
                        <LiveToolStatusStrip
                          toolExecutions={toolExecutions}
                          currentNode={currentNode}
                          loading={loading}
                        />
                      ) : null}
                      <MessageAttachmentStrip
                        attachments={message.attachments || []}
                        align="start"
                        onImageSelect={onImageSelect}
                      />
                      <div className="px-1 py-1 text-[14px] leading-7 text-[#e7e7f0]">
                        <MarkdownContent content={message.content} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        : null}

      {loading ? (
        <div className="flex w-full justify-start">
          <div className="flex w-full max-w-[680px] items-start gap-4">
            <div className="relative mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[#7000ff] text-white shadow-[0px_0px_0px_2px_rgba(172,137,255,0.2)]">
              <span
                aria-hidden
                className="absolute inset-0 rounded-[12px] ring-2 ring-[rgba(143,245,255,0.55)] animate-ping"
              />
              <Bot size={14} className="relative" />
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-3">
              {shouldShowStandaloneToolStrip ? (
                <LiveToolStatusStrip
                  toolExecutions={toolExecutions}
                  currentNode={currentNode}
                  loading={loading}
                />
              ) : null}
              <div
                role="status"
                aria-live="polite"
                className="flex items-center gap-2 px-1 py-1 text-[14px] italic text-[rgba(143,245,255,0.92)]"
              >
                <span
                  aria-hidden
                  className="relative flex h-2 w-2 shrink-0"
                >
                  <span className="absolute inline-flex h-full w-full rounded-full bg-[#8ff5ff] opacity-70 animate-ping" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[#8ff5ff]" />
                </span>
                <span className="truncate animate-pulse">
                  {currentNode || 'Coordinating team'}
                </span>
                <span aria-hidden className="inline-flex items-center gap-0.5">
                  <span
                    className="h-1 w-1 rounded-full bg-[#8ff5ff] animate-bounce"
                    style={{ animationDelay: '0ms' }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-[#8ff5ff] animate-bounce"
                    style={{ animationDelay: '160ms' }}
                  />
                  <span
                    className="h-1 w-1 rounded-full bg-[#8ff5ff] animate-bounce"
                    style={{ animationDelay: '320ms' }}
                  />
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isInterrupted ? (
        <div className="flex w-full justify-start">
          <div className="flex w-full max-w-[680px] items-start gap-4">
            <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(245,158,11,0.14)] text-amber-300">
              <Bot size={14} />
            </div>
            <div className="w-full">
              <HITLPanel
                onAction={onResume}
                loading={loading}
                reason={currentNode || null}
              />
            </div>
          </div>
        </div>
      ) : null}

      {!!streamError && !loading ? (
        <div className="flex w-full justify-start">
          <div className="flex w-full max-w-[680px] items-start gap-4">
            <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(239,68,68,0.14)] text-red-300">
              <Bot size={14} />
            </div>
            <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-5 py-4 text-sm text-red-200">
              {streamError}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

export default MessageThreadView;
