"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useEffect, useState } from 'react';
import { Loader2, LogIn } from 'lucide-react';

import { loginUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, refreshUser } = useAuth();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!loading && user) {
      router.replace('/');
    }
  }, [loading, router, user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await loginUser({ loginId, password });
      await refreshUser();
      router.replace('/');
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthScaffold
      title="Log In"
      subtitle="Enter your credential to access the cockpit."
      footer={(
        <>
          Need an account?{' '}
          <Link href="/signup" className="font-semibold text-[#8ff5ff] transition hover:text-[#c7fbff]">
            Sign up
          </Link>
        </>
      )}
    >
      <form className="space-y-5" onSubmit={handleSubmit}>
        <div className="mb-6 text-center">
          <h2 className="font-[var(--font-display)] text-[20px] font-bold text-[#e7e7f0]">
            Launch App
          </h2>
          <p className="mt-2 text-[13px] leading-6 text-[rgba(170,170,179,0.78)]">
            Authenticate to enter the orchestration workspace.
          </p>
        </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="login-id">
              Login ID
            </label>
            <input
              id="login-id"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Enter your login ID"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-[12px] font-semibold uppercase tracking-[0.2em] text-[rgba(170,170,179,0.82)]" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-black/70 px-4 py-4 text-sm text-[#e7e7f0] outline-none transition placeholder:text-[rgba(170,170,179,0.42)] focus:border-[rgba(143,245,255,0.28)]"
              placeholder="Enter your password"
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
            aria-label="Log In"
            disabled={submitting || !loginId.trim() || !password}
            className="inline-flex w-full items-center justify-center gap-2 rounded-[16px] bg-gradient-to-r from-[#8ff5ff] to-[#00deec] px-4 py-4 text-sm font-semibold text-[#005359] transition hover:brightness-105 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
            <span>LAUNCH APP</span>
          </button>
      </form>
    </AuthScaffold>
  );
}
