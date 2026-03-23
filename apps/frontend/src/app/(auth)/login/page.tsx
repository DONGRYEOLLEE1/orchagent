"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React, { useEffect, useState } from 'react';
import { Bot, Loader2, LogIn } from 'lucide-react';

import { loginUser } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

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
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-12 text-slate-100">
      <div className="w-full max-w-md rounded-3xl border border-slate-800/80 bg-slate-900/70 p-8 shadow-2xl shadow-black/40 backdrop-blur-xl">
        <div className="mb-8 flex items-center gap-4">
          <div className="rounded-2xl bg-blue-600 p-3 shadow-lg shadow-blue-500/20">
            <Bot className="text-white" />
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">OrchAgent</div>
            <h1 className="mt-1 text-2xl font-bold text-slate-100">Log In</h1>
          </div>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="login-id">
              Login ID
            </label>
            <input
              id="login-id"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Enter your login ID"
              disabled={submitting}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-blue-500/60"
              placeholder="Enter your password"
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
            disabled={submitting || !loginId.trim() || !password}
            className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
            <span>Log In</span>
          </button>
        </form>

        <p className="mt-6 text-sm text-slate-500">
          Need an account?{' '}
          <Link href="/signup" className="font-medium text-blue-400 transition hover:text-blue-300">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
