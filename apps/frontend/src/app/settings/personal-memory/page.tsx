"use client";

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';
import { PersonalMemoryPanel } from '@/components/settings/PersonalMemoryPanel';
import { SettingsShell } from '@/components/settings/SettingsShell';

function SettingsLoadingScreen({ message }: { message: string }) {
  return (
    <AuthScaffold title="Settings" subtitle={message}>
      <div className="text-sm text-[rgba(170,170,179,0.76)]">{message}</div>
    </AuthScaffold>
  );
}

export default function SettingsPersonalMemoryPage() {
  const router = useRouter();
  const { user, loading, updateUser, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [loading, router, user]);

  if (loading) {
    return <SettingsLoadingScreen message="Loading personal memory..." />;
  }

  if (!user) {
    return <SettingsLoadingScreen message="Redirecting to login..." />;
  }

  return (
    <SettingsShell
      currentUser={user}
      activeSection="personal-memory"
      title="Personal Memory"
      description="Stable preferences and tendencies extracted from your own requests are listed here so you can audit, keep, or delete them without guesswork."
      onLogout={async () => {
        await logout();
        router.replace('/login');
      }}
      onUserUpdated={updateUser}
    >
      <PersonalMemoryPanel />
    </SettingsShell>
  );
}
