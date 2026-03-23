"use client";

import React, { createContext, useContext, useEffect, useState } from 'react';

import { fetchCurrentUser, logoutUser, UnauthorizedError } from '@/lib/api';
import type { AuthUser } from '@/types/auth';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  error: string;
  refreshUser: () => Promise<AuthUser | null>;
  setUser: React.Dispatch<React.SetStateAction<AuthUser | null>>;
  updateUser: (user: AuthUser) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refreshUser = async (): Promise<AuthUser | null> => {
    setLoading(true);
    try {
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
      setError('');
      return currentUser;
    } catch (authError) {
      if (authError instanceof UnauthorizedError) {
        setUser(null);
        setError('');
        return null;
      }

      setUser(null);
      setError(authError instanceof Error ? authError.message : 'Unknown error');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    try {
      await logoutUser();
    } finally {
      setUser(null);
    }
  };

  const updateUser = (nextUser: AuthUser) => {
    setUser(nextUser);
  };

  useEffect(() => {
    void refreshUser();
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      setLoading(false);
      setError('');
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, refreshUser, setUser, updateUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
