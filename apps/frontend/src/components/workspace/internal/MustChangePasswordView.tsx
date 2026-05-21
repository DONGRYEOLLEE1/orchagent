import React, { useState } from 'react';
import { Loader2, Send } from 'lucide-react';

import { AuthScaffold } from '@/components/auth/AuthScaffold';
import { changePasswordUser } from '@/lib/api';
import type { AuthUser } from '@/types/auth';

export interface MustChangePasswordViewProps {
  currentUser: AuthUser;
  onPasswordChanged: () => Promise<unknown>;
  onLogout: () => Promise<void> | void;
}

export function MustChangePasswordView({
  currentUser,
  onPasswordChanged,
  onLogout,
}: MustChangePasswordViewProps) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await changePasswordUser({ currentPassword, newPassword });
      await onPasswordChanged();
    } catch (passwordError) {
      setError(passwordError instanceof Error ? passwordError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthScaffold
      title="Change Your Password"
      subtitle={`The bootstrap admin account is active as ${currentUser.login_id}. Replace the temporary password before using the workspace.`}
      footer={(
        <button
          type="button"
          onClick={() => void onLogout()}
          className="font-semibold text-[#8ff5ff] transition hover:text-[#c7fbff]"
        >
          Log Out
        </button>
      )}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="current-password">
              Current Password
            </label>
            <input
              id="current-password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Enter the current password"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="new-password">
              New Password
            </label>
            <input
              id="new-password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Create a new password"
              disabled={submitting}
            />
            <p className="mt-2 text-xs italic leading-5 text-[rgba(170,170,179,0.68)]">
              Password must be at least 4 characters and include lowercase letters and numbers.
            </p>
          </div>

          {error ? (
            <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !currentPassword || !newPassword}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-4 py-4 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            <span>Change Password</span>
          </button>
      </form>
    </AuthScaffold>
  );
}

export default MustChangePasswordView;
