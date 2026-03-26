"use client";

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';
import { ProfilePanel } from '@/components/auth/ProfilePanel';
import { ChangePasswordPanel } from '@/components/settings/ChangePasswordPanel';
import { SettingsShell } from '@/components/settings/SettingsShell';

function SettingsLoadingScreen({ message }: { message: string }) {
  return (
    <AuthScaffold title="Settings" subtitle={message}>
      <div className="text-sm text-[rgba(170,170,179,0.76)]">{message}</div>
    </AuthScaffold>
  );
}

export default function SettingsProfilePage() {
  const router = useRouter();
  const { user, loading, updateUser, refreshUser, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [loading, router, user]);

  if (loading) {
    return <SettingsLoadingScreen message="Restoring settings access..." />;
  }

  if (!user) {
    return <SettingsLoadingScreen message="Redirecting to login..." />;
  }

  return (
    <SettingsShell
      currentUser={user}
      activeSection="profile"
      title="Profile & Password"
      description="Keep profile metadata clean, and separate password changes into an explicit credential update surface instead of burying them in a drawer."
      onLogout={async () => {
        await logout();
        router.replace('/login');
      }}
      onUserUpdated={updateUser}
    >
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <ProfilePanel user={user} onUserUpdated={updateUser} />
        <ChangePasswordPanel onPasswordChanged={refreshUser} />
      </div>
    </SettingsShell>
  );
}
