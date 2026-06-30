// app/auth/login/page.tsx — Login page.

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand-purple to-brand-cyan text-xl font-black text-white mb-4">
            M
          </div>
          <h1 className="text-2xl font-bold text-white">Welcome back</h1>
          <p className="text-sm text-fg-400 mt-1">Sign in to your Maestro workspace</p>
        </div>

        <form onSubmit={handleSubmit} className="panel p-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-semibold text-fg-300 mb-1.5">Email</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none focus:ring-2 focus:ring-brand-purple/20"
              placeholder="you@company.com" />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-semibold text-fg-300 mb-1.5">Password</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none focus:ring-2 focus:ring-brand-purple/20"
              placeholder="********" />
          </div>
          {error && <p className="text-sm text-brand-rose" role="alert">{error}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary w-full justify-center disabled:opacity-50">
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="text-center text-sm text-fg-400">
          New to Maestro? <button onClick={() => router.push('/auth/register')} className="text-brand-purple hover:underline">Create an account</button>
        </p>
      </div>
    </div>
  );
}
