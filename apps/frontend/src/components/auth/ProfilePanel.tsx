"use client";

import React, { useEffect, useState } from 'react';
import { Loader2, Save, UserCircle2 } from 'lucide-react';

import { patchCurrentUser } from '@/lib/api';
import type { AuthUser } from '@/types/auth';

export function ProfilePanel({
  user,
  onUserUpdated,
}: {
  user: AuthUser;
  onUserUpdated: (user: AuthUser) => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name || '');
  const [email, setEmail] = useState(user.email || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setDisplayName(user.display_name || '');
    setEmail(user.email || '');
  }, [user.display_name, user.email]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const updatedUser = await patchCurrentUser({
        displayName,
        email,
      });
      onUserUpdated(updatedUser);
    } catch (profileError) {
      setError(profileError instanceof Error ? profileError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSave}
      className="rounded-2xl border border-slate-800/70 bg-slate-900/40 p-4"
    >
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-300">
        <UserCircle2 size={16} className="text-blue-400" />
        <span>Profile</span>
      </div>

      <div className="space-y-3">
        <div>
          <label
            htmlFor="profile-display-name"
            className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-500"
          >
            Display Name
          </label>
          <input
            id="profile-display-name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
            placeholder="Set a display name"
            disabled={submitting}
          />
        </div>

        <div>
          <label
            htmlFor="profile-email"
            className="mb-1 block text-xs uppercase tracking-[0.18em] text-slate-500"
          >
            Email
          </label>
          <input
            id="profile-email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
            placeholder="Set an email"
            disabled={submitting}
          />
        </div>
      </div>

      {error ? (
        <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {error}
        </div>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500"
      >
        {submitting ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
        <span>Save Profile</span>
      </button>
    </form>
  );
}
