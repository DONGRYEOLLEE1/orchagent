"use client";

import React, { useState } from 'react';
import { Loader2, ShieldAlert } from 'lucide-react';

import { patchAdminUser } from '@/lib/api';

export function AdminStatusPanel() {
  const [targetUserId, setTargetUserId] = useState('');
  const [status, setStatus] = useState('disabled');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const updatedUser = await patchAdminUser({ userId: targetUserId, status });
      setMessage(`Updated ${updatedUser.login_id} to ${updatedUser.status}.`);
    } catch (adminError) {
      setError(adminError instanceof Error ? adminError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4"
    >
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-amber-100">
        <ShieldAlert size={16} className="text-amber-300" />
        <span>Admin User Status</span>
      </div>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs uppercase tracking-[0.18em] text-amber-200/60">
            Target User ID
          </label>
          <input
            value={targetUserId}
            onChange={(e) => setTargetUserId(e.target.value)}
            className="w-full rounded-xl border border-amber-500/10 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/50"
            placeholder="Enter a user id"
            disabled={submitting}
          />
        </div>

        <div>
          <label className="mb-1 block text-xs uppercase tracking-[0.18em] text-amber-200/60">
            Status
          </label>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-full rounded-xl border border-amber-500/10 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-amber-400/50"
            disabled={submitting}
          >
            <option value="disabled">disabled</option>
            <option value="active">active</option>
          </select>
        </div>
      </div>

      {message ? (
        <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {message}
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      ) : null}

      <button
        type="submit"
        disabled={submitting || !targetUserId.trim()}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-amber-500 px-3 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:bg-slate-800 disabled:text-slate-500"
      >
        {submitting ? <Loader2 size={14} className="animate-spin" /> : <ShieldAlert size={14} />}
        <span>Update Status</span>
      </button>
    </form>
  );
}
