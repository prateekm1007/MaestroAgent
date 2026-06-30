// app/page.tsx — Root page (redirects to dashboard or login).

'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      router.push(user ? '/dashboard' : '/auth/login');
    }
  }, [user, loading, router]);

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
