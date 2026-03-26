"use client";

import { useState } from 'react';
import { KeyRound, Loader2, ShieldCheck } from 'lucide-react';

import { changePasswordUser } from '@/lib/api';

export function ChangePasswordPanel({
  onPasswordChanged,
}: {
  onPasswordChanged?: () => Promise<unknown> | unknown;
}) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const passwordsMatch = !confirmPassword || newPassword === confirmPassword;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!passwordsMatch) {
      setError('New password confirmation does not match.');
      return;
    }

    setSubmitting(true);
    setError('');
    setSuccess('');
    try {
      await changePasswordUser({ currentPassword, newPassword });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setSuccess('Password updated. Your current session has been refreshed.');
      await onPasswordChanged?.();
    } catch (passwordError) {
      setError(passwordError instanceof Error ? passwordError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(18,22,32,0.76)] px-5 py-5">
      <div className="flex items-center gap-3">
        <span className="inline-flex rounded-[14px] bg-[rgba(0,240,255,0.08)] p-2 text-[#8ff5ff]">
          <KeyRound size={16} />
        </span>
        <div>
          <h2 className="text-[18px] font-semibold text-white">Change Password</h2>
          <p className="mt-1 text-[12px] leading-6 text-[rgba(170,170,179,0.74)]">
            Keep credential updates explicit. Confirm the new password before the session rotates.
          </p>
        </div>
      </div>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(170,170,179,0.72)]">
              Current Password
            </span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              disabled={submitting}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-[rgba(7,10,16,0.86)] px-4 py-3 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.4)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Enter current password"
            />
          </label>

          <div className="rounded-[18px] border border-[rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.03)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.74)]">
            Passwords must be at least 4 characters and include lowercase letters plus numbers. Reusing the current password is blocked.
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(170,170,179,0.72)]">
              New Password
            </span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              disabled={submitting}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-[rgba(7,10,16,0.86)] px-4 py-3 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.4)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Create a new password"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(170,170,179,0.72)]">
              Confirm Password
            </span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              disabled={submitting}
              className={[
                'w-full rounded-[16px] border bg-[rgba(7,10,16,0.86)] px-4 py-3 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.4)]',
                passwordsMatch
                  ? 'border-[rgba(255,255,255,0.08)] focus:border-[rgba(143,245,255,0.28)]'
                  : 'border-red-500/40 focus:border-red-400/70',
              ].join(' ')}
              placeholder="Re-enter the new password"
            />
          </label>
        </div>

        {!passwordsMatch ? (
          <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            New password confirmation does not match.
          </div>
        ) : null}

        {error ? (
          <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        ) : null}

        {success ? (
          <div className="rounded-[16px] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            <span className="inline-flex items-center gap-2">
              <ShieldCheck size={15} />
              {success}
            </span>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={submitting || !currentPassword || !newPassword || !confirmPassword || !passwordsMatch}
          className="inline-flex items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-5 py-3 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-500"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
          <span>Change Password</span>
        </button>
      </form>
    </section>
  );
}
