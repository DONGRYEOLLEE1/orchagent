import React from 'react';
import { Loader2 } from 'lucide-react';

export interface AuthLoadingScreenProps {
  message: string;
}

export const AuthLoadingScreen = ({ message }: AuthLoadingScreenProps) => (
  <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
    <div className="rounded-3xl border border-slate-800 bg-slate-900/70 px-8 py-7 shadow-2xl shadow-black/40 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <Loader2 size={18} className="animate-spin text-blue-400" />
        <span className="text-sm text-slate-300">{message}</span>
      </div>
    </div>
  </main>
);

export default AuthLoadingScreen;
