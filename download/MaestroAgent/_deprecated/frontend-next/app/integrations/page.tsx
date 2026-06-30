// app/integrations/page.tsx — Integrations page.

'use client';

import { useEffect, useState } from 'react';
import { integrations as integrationsApi } from '@/lib/api';
import type { Integration } from '@/types';
import { Plug, CheckCircle, XCircle } from 'lucide-react';

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { integrationsApi.list().then(setIntegrations).catch(() => {}).finally(() => setLoading(false)); }, []);

  const connect = async (provider: 'jira' | 'github' | 'slack') => {
    const fn = provider === 'jira' ? integrationsApi.jiraAuthUrl : provider === 'github' ? integrationsApi.githubAuthUrl : integrationsApi.slackAuthUrl;
    const { auth_url } = await fn();
    window.location.href = auth_url;
  };

  const providers = [
    { id: 'jira', name: 'Jira', icon: '🎯', description: 'Issue tracking and project management' },
    { id: 'github', name: 'GitHub', icon: '🐙', description: 'Code execution, PR reviews, and repository management' },
    { id: 'slack', name: 'Slack', icon: '💬', description: 'Notifications, approvals, and team communication' },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Plug className="w-5 h-5 text-brand-cyan" />
        <h1 className="text-2xl font-bold text-white">Integrations</h1>
      </div>
      {loading ? <p className="text-fg-400">Loading...</p> : (
        <div className="space-y-3">
          {providers.map((p) => {
            const integration = integrations.find((i) => i.providerId === p.id);
            const connected = integration?.status === 'connected';
            return (
              <div key={p.id} className="panel p-4 flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-white/[0.04] flex items-center justify-center text-xl">{p.icon}</div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-fg-100">{p.name}</div>
                  <div className="text-xs text-fg-500">{p.description}</div>
                  {integration && <div className="text-[10px] text-fg-500 mt-0.5">{integration.eventsReceived} events received</div>}
                </div>
                {connected ? (
                  <div className="flex items-center gap-2"><CheckCircle className="w-4 h-4 text-brand-cyan" /><span className="tag tag-cyan">Connected</span></div>
                ) : (
                  <button onClick={() => connect(p.id as any)} className="btn btn-primary">Connect</button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
