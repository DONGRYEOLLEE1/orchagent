import React, { useState } from 'react';
import { AlertTriangle, Check, X, Send } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const HITLPanel = ({
  onAction,
  loading
}: {
  onAction: (action: string, feedback: string) => void,
  loading: boolean
}) => {
  const [feedback, setFeedback] = useState('');

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-6 mt-4 shadow-lg shadow-amber-500/5 animate-in fade-in slide-in-from-bottom-2">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-amber-500/20 rounded-full text-amber-400">
          <AlertTriangle size={20} />
        </div>
        <h3 className="text-lg font-bold text-amber-100">Action Required</h3>
      </div>
      <p className="text-amber-200/80 text-sm mb-6">
        The agent has paused execution and requires your approval to proceed.
        Please review the proposed plan or action and provide feedback.
      </p>

      <div className="flex flex-col gap-4">
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Optional: Provide feedback or specific instructions..."
          className="w-full bg-black/40 border border-amber-500/20 rounded-xl p-3 text-sm text-amber-50 placeholder:text-amber-500/40 focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none h-24"
          disabled={loading}
        />

        <div className="flex gap-3 justify-end">
          <button
            onClick={() => onAction('reject', feedback)}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <X size={16} />
            Reject
          </button>

          <button
            onClick={() => onAction(feedback ? 'feedback' : 'approve', feedback)}
            disabled={loading}
            className={cn(
              "flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50",
              feedback
                ? "bg-amber-500 hover:bg-amber-600 text-white"
                : "bg-emerald-600 hover:bg-emerald-500 text-white"
            )}
          >
            {feedback ? <Send size={16} /> : <Check size={16} />}
            {feedback ? 'Send Feedback' : 'Approve & Continue'}
          </button>
        </div>
      </div>
    </div>
  );
};
