"use client";

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { useAuth } from '@/components/auth/AuthProvider';
import { AuthScaffold } from '@/components/auth/AuthScaffold';
import { PersonalizationPanel } from '@/components/settings/PersonalizationPanel';
import { SettingsShell } from '@/components/settings/SettingsShell';

function SettingsLoadingScreen({ message }: { message: string }) {
  return (
    <AuthScaffold title="Settings" subtitle={message}>
      <div className="text-sm text-[rgba(170,170,179,0.76)]">{message}</div>
    </AuthScaffold>
  );
}

export default function SettingsPersonalizationPage() {
  const router = useRouter();
  const { user, loading, updateUser, logout } = useAuth();

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login');
    }
  }, [loading, router, user]);

  if (loading) {
    return <SettingsLoadingScreen message="Loading personalization..." />;
  }

  if (!user) {
    return <SettingsLoadingScreen message="Redirecting to login..." />;
  }

  return (
    <SettingsShell
      currentUser={user}
      activeSection="personalization"
      title="Personalization"
      description="Fine-tune your AI agent's responses by providing context about yourself and your preferred communication style."
      onLogout={async () => {
        await logout();
        router.replace('/login');
      }}
      onUserUpdated={updateUser}
    >
      <PersonalizationPanel />
    </SettingsShell>
  );
}
