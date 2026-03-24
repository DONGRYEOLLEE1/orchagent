"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, UserPlus } from 'lucide-react';

import { signupUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';

function passwordStrength(password: string) {
  let score = 0;
  if (password.length >= 4) score += 1;
  if (/[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;

  if (score <= 1) return { label: 'Weak', tone: 'bg-red-500' };
  if (score === 2) return { label: 'Moderate', tone: 'bg-amber-500' };
  return { label: 'Strong', tone: 'bg-emerald-500' };
}

export default function SignupPage() {
  const router = useRouter();
  const { user, loading, refreshUser } = useAuth();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const strength = useMemo(() => passwordStrength(password), [password]);

  useEffect(() => {
    if (!loading && user) {
      router.replace('/');
    }
  }, [loading, router, user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Password confirmation does not match.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await signupUser({ loginId, password });
      await refreshUser();
      router.replace('/');
    } catch (signupError) {
      setError(signupError instanceof Error ? signupError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthScaffold
      title="Create Account"
      subtitle="Provision a new operator identity for the workspace."
      footer={(
        <>
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-[#8ff5ff] transition hover:text-[#c7fbff]">
            Log in
          </Link>
        </>
      )}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="signup-login-id">
              Login ID
            </label>
            <input
              id="signup-login-id"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Choose your login ID"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="signup-password">
              Password
            </label>
            <input
              id="signup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Create a password"
              disabled={submitting}
            />
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
              <div
                className={`h-full transition-all ${strength.tone}`}
                style={{ width: password ? `${Math.min(password.length * 16, 100)}%` : '0%' }}
              />
            </div>
            <div className="mt-2 text-xs font-medium text-[rgba(170,170,179,0.82)]">Strength: {strength.label}</div>
            <p className="mt-2 text-xs italic leading-5 text-[rgba(170,170,179,0.68)]">
              Password must be at least 4 characters and include lowercase letters and numbers.
            </p>
          </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="signup-confirm-password">
              Confirm Password
            </label>
            <input
              id="signup-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Re-enter your password"
              disabled={submitting}
            />
          </div>

          {error ? (
            <div className="rounded-[16px] border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !loginId.trim() || !password || !confirmPassword}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-4 py-4 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
            <span>Create Account</span>
          </button>
      </form>
    </AuthScaffold>
  );
}
