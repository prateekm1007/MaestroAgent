// components/layout/dashboard-layout.tsx — Layout wrapper for authenticated pages.

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Sidebar } from './sidebar';

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.push('/auth/login');
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex gap-1">
          <span className="w-2 h-2 rounded-full bg-brand-purple typing-dot" />
          <span className="w-2 h-2 rounded-full bg-brand-purple typing-dot" />
          <span className="w-2 h-2 rounded-full bg-brand-purple typing-dot" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
