// app/settings/page.tsx — Settings page.

'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { auth as authApi } from '@/lib/api';
import type { OrgMember, AuditLogEntry } from '@/types';
import { User, Users, Key, ScrollText, Shield } from 'lucide-react';

export default function SettingsPage() {
  const { user } = useAuth();
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [apiKeys, setApiKeys] = useState<any[]>([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyResult, setNewKeyResult] = useState<string | null>(null);
  const [tab, setTab] = useState<'profile' | 'members' | 'api-keys' | 'audit'>('profile');

  useEffect(() => {
    authApi.listUsers().then(({ members }) => setMembers(members)).catch(() => {});
    authApi.getAuditLog().then(({ entries }) => setAuditLog(entries)).catch(() => {});
    authApi.listApiKeys().then(({ api_keys }) => setApiKeys(api_keys)).catch(() => {});
  }, []);

  const createKey = async () => {
    if (!newKeyName) return;
    const result = await authApi.createApiKey({ name: newKeyName });
    setNewKeyResult(result.key);
    setNewKeyName('');
    authApi.listApiKeys().then(({ api_keys }) => setApiKeys(api_keys));
  };

  const revokeKey = async (id: string) => {
    await authApi.revokeApiKey(id);
    authApi.listApiKeys().then(({ api_keys }) => setApiKeys(api_keys));
  };

  const tabs = [
    { id: 'profile' as const, label: 'Profile', icon: User },
    { id: 'members' as const, label: 'Members', icon: Users },
    { id: 'api-keys' as const, label: 'API Keys', icon: Key },
    { id: 'audit' as const, label: 'Audit Log', icon: ScrollText },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>
      <div className="flex gap-1 border-b border-white/[0.06]">
        {tabs.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold transition-all border-b-2 ${tab === t.id ? 'text-[#a594ff] border-brand-purple' : 'text-fg-400 border-transparent hover:text-fg-200'}`}>
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>

      {tab === 'profile' && user && (
        <div className="panel p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div><span className="text-fg-500 block text-xs mb-1">Name</span><span className="text-fg-100 font-semibold">{user.name || '-'}</span></div>
            <div><span className="text-fg-500 block text-xs mb-1">Email</span><span className="text-fg-100 font-semibold">{user.email}</span></div>
            <div><span className="text-fg-500 block text-xs mb-1">Role</span><span className="tag tag-purple">{user.role}</span></div>
            <div><span className="text-fg-500 block text-xs mb-1">Organization</span><span className="text-fg-100 font-semibold">{user.org_name}</span></div>
            <div><span className="text-fg-500 block text-xs mb-1">Department</span><span className="text-fg-100 font-semibold">{user.department || '-'}</span></div>
            <div><span className="text-fg-500 block text-xs mb-1">Team</span><span className="text-fg-100 font-semibold">{user.team || '-'}</span></div>
          </div>
          <div>
            <span className="text-fg-500 block text-xs mb-2">Permissions ({user.permissions.length})</span>
            <div className="flex flex-wrap gap-1">
              {user.permissions.map((p) => <span key={p} className="tag tag-gray font-mono text-[9px]">{p}</span>)}
            </div>
          </div>
        </div>
      )}

      {tab === 'members' && (
        <div className="panel">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-white/[0.06] text-[10px] font-bold text-fg-500 uppercase tracking-wider">
              <th className="text-left px-4 py-3">Name</th><th className="text-left px-4 py-3">Email</th><th className="text-left px-4 py-3">Role</th><th className="text-left px-4 py-3">Joined</th>
            </tr></thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} className="border-b border-white/[0.04]">
                  <td className="px-4 py-3 text-fg-100">{m.name}</td>
                  <td className="px-4 py-3 text-fg-400">{m.email}</td>
                  <td className="px-4 py-3"><span className="tag tag-purple">{m.role}</span></td>
                  <td className="px-4 py-3 text-fg-400 text-xs">{m.joinedAt ? new Date(m.joinedAt).toLocaleDateString() : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'api-keys' && (
        <div className="space-y-4">
          {newKeyResult && (
            <div className="panel p-4 border-brand-cyan/30">
              <div className="text-xs font-bold text-brand-cyan uppercase tracking-wider mb-2">API Key Created - Copy Now</div>
              <code className="block bg-ink-950 p-3 rounded-lg text-xs text-brand-cyan font-mono break-all">{newKeyResult}</code>
              <button onClick={() => setNewKeyResult(null)} className="btn btn-ghost mt-2 text-xs">Dismiss</button>
            </div>
          )}
          <div className="panel p-4 flex gap-2">
            <input value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="Key name (e.g. CI/CD)" className="flex-1 bg-ink-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-fg-100 focus:border-brand-purple/40 focus:outline-none" />
            <button onClick={createKey} className="btn btn-primary">Create Key</button>
          </div>
          <div className="space-y-2">
            {apiKeys.map((k) => (
              <div key={k.id} className="panel p-3 flex items-center gap-3">
                <Key className="w-4 h-4 text-fg-400" />
                <div className="flex-1"><div className="text-sm text-fg-100">{k.name}</div><div className="text-[10px] text-fg-500 font-mono">{k.key_prefix}...{k.key_suffix}</div></div>
                <span className="text-[10px] text-fg-500">{k.last_used_at ? `Used ${new Date(k.last_used_at).toLocaleDateString()}` : 'Never used'}</span>
                <button onClick={() => revokeKey(k.id)} className="btn bg-brand-rose/12 text-brand-rose border border-brand-rose/25 text-xs">Revoke</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'audit' && (
        <div className="panel p-4 max-h-96 overflow-y-auto space-y-1 font-mono text-[11px]">
          {auditLog.map((e) => (
            <div key={e.id} className="flex gap-2 items-start py-0.5">
              <span className="text-fg-500 w-32 flex-shrink-0">{new Date(e.ts).toLocaleString()}</span>
              <span className={`tag ${e.success ? 'tag-cyan' : 'tag-rose'}`}>{e.action}</span>
              <span className="text-fg-400 truncate">{e.userEmail || 'system'} - {e.ipAddress || ''}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
