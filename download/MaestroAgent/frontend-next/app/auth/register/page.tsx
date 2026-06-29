// app/auth/register/page.tsx — Registration page.

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ email: '', password: '', name: '', org_name: '', org_slug: '', industry: 'technology' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (form.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      await register(form);
      router.push('/dashboard');
    } catch (err: any) { setError(err.message || 'Registration failed'); }
    finally { setLoading(false); }
  };

  const set = (k: string, v: string) => setForm(prev => ({ ...prev, [k]: v }));

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-center">
          <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand-purple to-brand-cyan text-xl font-black text-white mb-4">M</div>
          <h1 className="text-2xl font-bold text-white">Create your workspace</h1>
          <p className="text-sm text-fg-400 mt-1">Start executing work with Maestro</p>
        </div>
        <form onSubmit={handleSubmit} className="panel p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="name" className="block text-xs font-semibold text-fg-300 mb-1.5">Your Name</label>
              <input id="name" type="text" value={form.name} onChange={(e) => set('name', e.target.value)} required
                className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none" />
            </div>
            <div>
              <label htmlFor="email" className="block text-xs font-semibold text-fg-300 mb-1.5">Email</label>
              <input id="email" type="email" value={form.email} onChange={(e) => set('email', e.target.value)} required
                className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none" />
            </div>
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-semibold text-fg-300 mb-1.5">Password</label>
            <input id="password" type="password" value={form.password} onChange={(e) => set('password', e.target.value)} required
              className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="org_name" className="block text-xs font-semibold text-fg-300 mb-1.5">Organization Name</label>
              <input id="org_name" type="text" value={form.org_name} onChange={(e) => set('org_name', e.target.value)} required
                className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none" />
            </div>
            <div>
              <label htmlFor="org_slug" className="block text-xs font-semibold text-fg-300 mb-1.5">Org Slug</label>
              <input id="org_slug" type="text" value={form.org_slug} onChange={(e) => set('org_slug', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))} required
                className="w-full bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none font-mono" placeholder="acme-corp" />
            </div>
          </div>
          {error && <p className="text-sm text-brand-rose" role="alert">{error}</p>}
          <button type="submit" disabled={loading} className="btn btn-primary w-full justify-center disabled:opacity-50">
            {loading ? 'Creating workspace...' : 'Create workspace'}
          </button>
        </form>
        <p className="text-center text-sm text-fg-400">
          Already have an account? <button onClick={() => router.push('/auth/login')} className="text-brand-purple hover:underline">Sign in</button>
        </p>
      </div>
    </div>
  );
}
