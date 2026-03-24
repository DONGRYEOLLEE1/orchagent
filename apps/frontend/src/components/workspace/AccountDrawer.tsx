import { X } from 'lucide-react';

import type { AuthUser } from '@/types/auth';
import { AdminStatusPanel } from '@/components/auth/AdminStatusPanel';
import { ProfilePanel } from '@/components/auth/ProfilePanel';

export function AccountDrawer({
  user,
  onClose,
  onLogout,
  onUserUpdated,
}: {
  user: AuthUser;
  onClose: () => void;
  onLogout: () => Promise<void> | void;
  onUserUpdated: (user: AuthUser) => void;
}) {
  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Close account drawer"
        onClick={onClose}
        className="absolute inset-0 bg-[rgba(7,9,13,0.74)] backdrop-blur-sm"
      />

      <aside className="absolute inset-y-0 right-0 flex w-[min(28rem,100vw)] flex-col border-l border-[rgba(255,255,255,0.06)] bg-[rgba(12,14,20,0.96)] px-6 py-6 shadow-2xl shadow-black/50 backdrop-blur-xl">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.24em] text-[rgba(143,245,255,0.7)]">
              Account Control
            </div>
            <h2 className="mt-2 font-[var(--font-display)] text-[20px] font-bold text-[#e7e7f0]">
              {user.display_name || user.login_id}
            </h2>
            <p className="mt-1 text-[12px] text-[rgba(170,170,179,0.76)]">
              Manage your profile and operator permissions here.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(35,38,46,0.4)] p-2 text-[rgba(170,170,179,0.82)] transition hover:text-[#e7e7f0]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="mb-6 rounded-[12px] border border-[rgba(255,255,255,0.05)] bg-[rgba(29,31,40,0.48)] px-4 py-4 text-[12px] leading-6 text-[rgba(170,170,179,0.8)]">
          Thread telemetry panels stay focused on orchestration. Account management is moved here to keep the right sidebar product-facing.
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto pr-1">
          <ProfilePanel user={user} onUserUpdated={onUserUpdated} />
          {user.role === 'admin' ? <AdminStatusPanel /> : null}
        </div>

        <div className="mt-6 border-t border-[rgba(255,255,255,0.06)] pt-5">
          <button
            type="button"
            onClick={() => void onLogout()}
            className="inline-flex w-full items-center justify-center rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.5)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.16em] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.18)] hover:text-[#8ff5ff]"
          >
            Log Out
          </button>
        </div>
      </aside>
    </div>
  );
}
