import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { cn } from '@/lib/cn';
import { preprocessMarkdown } from '@/lib/markdown';

export interface MarkdownContentProps {
  content: string;
}

export const MarkdownContent = ({ content }: MarkdownContentProps) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
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
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="cursor-pointer break-all text-[#8ff5ff] underline decoration-[rgba(143,245,255,0.4)] underline-offset-3 transition hover:text-[#c7fbff] hover:decoration-[rgba(199,251,255,0.9)]"
          >
            {children}
          </a>
        ),
      }}
    >
      {preprocessMarkdown(content)}
    </ReactMarkdown>
  );
};

export default MarkdownContent;
