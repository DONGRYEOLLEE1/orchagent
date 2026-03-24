import type { ReactNode } from 'react';

import { Bot } from 'lucide-react';

export function AuthScaffold({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--oa-bg)] px-6 py-12 text-[var(--oa-copy)]">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-10%] top-[-6%] h-[24rem] w-[24rem] rounded-full bg-[rgba(143,245,255,0.09)] blur-[120px]" />
        <div className="absolute bottom-[-12%] right-[-6%] h-[24rem] w-[24rem] rounded-full bg-[rgba(172,137,255,0.12)] blur-[120px]" />
      </div>

      <div className="pointer-events-none absolute left-10 top-10 hidden text-[56px] font-bold tracking-[-0.08em] text-[rgba(255,255,255,0.06)] lg:block">
        01
      </div>
      <div className="pointer-events-none absolute right-10 top-10 text-[32px] font-bold tracking-[-0.08em] text-[rgba(255,255,255,0.06)]">
        LX
      </div>

      <div className="relative z-10 w-full max-w-[448px] rounded-[24px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.82)] px-10 py-10 shadow-2xl shadow-black/40 backdrop-blur-xl">
        <div className="mb-10 text-center">
          <div className="mx-auto mb-8 flex h-[58px] w-16 items-center justify-center rounded-[18px] border border-[rgba(172,137,255,0.18)] bg-[rgba(35,38,46,0.75)] text-[#ac89ff]">
            <Bot size={28} />
          </div>
          <div className="text-[11px] uppercase tracking-[0.26em] text-[rgba(172,137,255,0.84)]">
            OrchAgent
          </div>
          <h1 className="mt-4 font-[var(--font-display)] text-[30px] font-bold text-[#e7e7f0]">
            {title}
          </h1>
          <p className="mt-3 text-[14px] leading-7 text-[rgba(170,170,179,0.78)]">
            {subtitle}
          </p>
        </div>

        {children}

        {footer ? <div className="mt-8 text-center text-[14px] text-[rgba(170,170,179,0.76)]">{footer}</div> : null}
      </div>
    </main>
  );
}
