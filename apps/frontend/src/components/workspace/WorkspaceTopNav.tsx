"use client";

import React from 'react';
import { useRouter } from 'next/navigation';
import { Menu, PanelRightOpen } from 'lucide-react';

import type { AuthUser } from '@/types/auth';

type WorkspaceTopNavSection = 'chat' | 'dashboard' | 'settings';

function navButtonClass(active: boolean) {
  if (active) {
    return 'rounded-[8px] border-b-2 border-[#00f0ff] px-3 py-1 font-[var(--font-display)] text-[#00f0ff]';
  }

  return 'rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]';
}

export function WorkspaceTopNav({
  activeSection,
  currentUser,
  onOpenAccountDrawer,
  onOpenMobileSidebar,
}: {
  activeSection: WorkspaceTopNavSection;
  currentUser: AuthUser;
  onOpenAccountDrawer: () => void;
  onOpenMobileSidebar?: () => void;
}) {
  const router = useRouter();

  return (
    <header className="relative z-20 flex h-16 shrink-0 items-center justify-between border-b border-[rgba(255,255,255,0.05)] bg-[rgba(12,14,20,0.88)] px-6 backdrop-blur-xl md:px-8">
      <div className="flex min-w-0 items-center gap-4">
        {onOpenMobileSidebar ? (
          <button
            type="button"
            onClick={onOpenMobileSidebar}
            className="inline-flex rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.4)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0] lg:hidden"
          >
            <Menu size={16} />
          </button>
        ) : null}

        <div className="hidden items-center gap-8 md:flex">
          <div className="font-[var(--font-display)] text-[24px] font-bold tracking-[-0.04em] text-[#00f0ff]">
            OrchAgent
          </div>

          <nav className="flex items-center gap-2 text-[14px]">
            <button
              type="button"
              onClick={activeSection === 'chat' ? undefined : () => router.push('/')}
              className={navButtonClass(activeSection === 'chat')}
            >
              Chat
            </button>
            <button
              type="button"
              onClick={activeSection === 'dashboard' ? undefined : () => router.push('/dashboard')}
              className={navButtonClass(activeSection === 'dashboard')}
            >
              Dashboard
            </button>
            <button
              type="button"
              aria-disabled="true"
              className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
            >
              Agents
            </button>
            <button
              type="button"
              aria-disabled="true"
              className="rounded-[8px] px-3 py-1 text-[rgba(148,163,184,0.7)] transition hover:bg-[rgba(255,255,255,0.04)] hover:text-[#e7e7f0]"
            >
              Logs
            </button>
            <button
              type="button"
              onClick={activeSection === 'settings' ? undefined : () => router.push('/settings/profile')}
              className={navButtonClass(activeSection === 'settings')}
            >
              Settings
            </button>
          </nav>
        </div>

        <div className="md:hidden">
          <div className="font-[var(--font-display)] text-[18px] font-bold text-[#00f0ff]">
            OrchAgent
          </div>
        </div>
      </div>

      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          aria-label="Open account drawer"
          onClick={onOpenAccountDrawer}
          className="inline-flex items-center gap-2 rounded-[12px] border border-[rgba(143,245,255,0.16)] bg-[rgba(29,31,40,0.45)] px-3 py-2 text-[12px] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.3)]"
        >
          <PanelRightOpen size={15} className="text-[#8ff5ff]" />
          <span className="hidden font-semibold sm:inline">
            {currentUser.display_name || currentUser.login_id}
          </span>
        </button>
      </div>
    </header>
  );
}
