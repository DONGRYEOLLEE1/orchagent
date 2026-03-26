"use client";

import Link from 'next/link';
import { useState } from 'react';
import { BrainCircuit, KeyRound, UserCircle2 } from 'lucide-react';

import type { AuthUser } from '@/types/auth';
import { AccountDrawer } from '@/components/workspace/AccountDrawer';
import { WorkspaceTopNav } from '@/components/workspace/WorkspaceTopNav';

type SettingsSection = 'profile' | 'personal-memory';

const SECTIONS: Array<{
  id: SettingsSection;
  href: string;
  label: string;
  description: string;
  icon: typeof UserCircle2;
}> = [
  {
    id: 'profile',
    href: '/settings/profile',
    label: 'Profile',
    description: 'Identity, email, and password controls',
    icon: UserCircle2,
  },
  {
    id: 'personal-memory',
    href: '/settings/personal-memory',
    label: 'Personal Memory',
    description: 'Durable preferences and personalization memory',
    icon: BrainCircuit,
  },
];

export function SettingsShell({
  currentUser,
  activeSection,
  title,
  description,
  onLogout,
  onUserUpdated,
  children,
}: {
  currentUser: AuthUser;
  activeSection: SettingsSection;
  title: string;
  description: string;
  onLogout: () => Promise<void> | void;
  onUserUpdated: (user: AuthUser) => void;
  children: React.ReactNode;
}) {
  const [accountPanelOpen, setAccountPanelOpen] = useState(false);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(0,240,255,0.12),_transparent_22%),linear-gradient(180deg,#090b11_0%,#0c0f17_48%,#111522_100%)] text-[#e7e7f0]">
      {accountPanelOpen ? (
        <AccountDrawer
          user={currentUser}
          onClose={() => setAccountPanelOpen(false)}
          onLogout={onLogout}
          onUserUpdated={onUserUpdated}
        />
      ) : null}

      <WorkspaceTopNav
        activeSection="settings"
        currentUser={currentUser}
        onOpenAccountDrawer={() => setAccountPanelOpen(true)}
      />

      <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-8 px-5 pb-12 pt-8 md:px-8 lg:flex-row lg:gap-10 lg:px-10">
        <aside className="lg:w-[270px] lg:shrink-0">
          <div className="rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(14,17,26,0.82)] p-5 shadow-[0_20px_80px_rgba(0,0,0,0.35)] backdrop-blur-xl">
            <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.72)]">
              Settings
            </div>
            <div className="mt-3 font-[var(--font-display)] text-[28px] font-semibold tracking-[-0.05em] text-white">
              Account Control
            </div>
            <p className="mt-2 max-w-[22rem] text-[13px] leading-6 text-[rgba(170,170,179,0.76)]">
              Profile identity, credential posture, and personalization memory all live here in one consistent control surface.
            </p>

            <div className="mt-8 space-y-2">
              {SECTIONS.map((section) => {
                const Icon = section.icon;
                const active = section.id === activeSection;
                return (
                  <Link
                    key={section.id}
                    href={section.href}
                    className={[
                      'group flex items-start gap-3 rounded-[18px] px-4 py-3 transition',
                      active
                        ? 'bg-[rgba(0,240,255,0.08)] text-white shadow-[inset_0_0_0_1px_rgba(143,245,255,0.18)]'
                        : 'text-[rgba(170,170,179,0.82)] hover:bg-[rgba(255,255,255,0.035)] hover:text-white',
                    ].join(' ')}
                  >
                    <span className={[
                      'mt-0.5 inline-flex rounded-[12px] p-2 transition',
                      active
                        ? 'bg-[rgba(0,240,255,0.12)] text-[#8ff5ff]'
                        : 'bg-[rgba(255,255,255,0.04)] text-[rgba(170,170,179,0.68)] group-hover:text-[#e7e7f0]',
                    ].join(' ')}>
                      <Icon size={15} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[14px] font-semibold">{section.label}</span>
                      <span className="mt-1 block text-[11px] leading-5 text-[rgba(170,170,179,0.7)]">
                        {section.description}
                      </span>
                    </span>
                  </Link>
                );
              })}
            </div>

            <div className="mt-8 rounded-[18px] border border-[rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.03)] px-4 py-4">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(143,245,255,0.72)]">
                <KeyRound size={13} />
                Security Posture
              </div>
              <div className="mt-3 text-[13px] leading-6 text-[rgba(170,170,179,0.74)]">
                Password rotation stays separated from profile identity so credential changes remain visible, deliberate, and reversible.
              </div>
            </div>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <div className="rounded-[28px] border border-[rgba(255,255,255,0.06)] bg-[rgba(11,14,22,0.78)] px-6 py-6 shadow-[0_30px_90px_rgba(0,0,0,0.38)] backdrop-blur-xl md:px-8 md:py-8">
            <div className="max-w-[48rem]">
              <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.72)]">
                Settings / {activeSection === 'profile' ? 'Profile' : 'Personal Memory'}
              </div>
              <h1 className="mt-3 font-[var(--font-display)] text-[34px] font-semibold tracking-[-0.06em] text-white md:text-[42px]">
                {title}
              </h1>
              <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.8)]">
                {description}
              </p>
            </div>

            <div className="mt-8">{children}</div>
          </div>
        </section>
      </div>
    </main>
  );
}
