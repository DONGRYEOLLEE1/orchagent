"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, UserPlus } from 'lucide-react';

import { signupUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

function passwordStrength(password: string) {
  let score = 0;
  if (password.length >= 15) score += 1;
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
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-12 text-slate-100">
      <div className="w-full max-w-md rounded-3xl border border-slate-800/80 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 backdrop-blur-xl">
        <div className="mb-8 flex items-center gap-4">
          <div className="rounded-2xl bg-blue-600 p-3 shadow-lg shadow-blue-500/20">
            <Bot className="text-white" />
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">OrchAgent</div>
            <h1 className="mt-1 text-2xl font-bold text-slate-100">Create Account</h1>
          </div>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="signup-login-id">
              Login ID
            </label>
            <input
              id="signup-login-id"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Choose your login ID"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="signup-password">
              Password
            </label>
            <input
              id="signup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Create a password"
              disabled={submitting}
            />
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full transition-all ${strength.tone}`}
                style={{ width: password ? `${Math.min(password.length * 6, 100)}%` : '0%' }}
              />
            </div>
            <div className="mt-2 text-xs font-medium text-slate-400">Strength: {strength.label}</div>
            <p className="mt-2 text-xs italic leading-5 text-slate-500">
              Password must be at least 4 characters and include lowercase letters and numbers.
            </p>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="signup-confirm-password">
              Confirm Password
            </label>
            <input
              id="signup-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Re-enter your password"
              disabled={submitting}
            />
          </div>

          {error ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !loginId.trim() || !password || !confirmPassword}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />}
            <span>Create Account</span>
          </button>
        </form>

        <p className="mt-6 text-sm text-slate-500">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-blue-400 transition hover:text-blue-300">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
