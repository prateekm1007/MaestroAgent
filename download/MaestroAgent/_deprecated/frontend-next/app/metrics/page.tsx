// app/metrics/page.tsx — Metrics dashboard.

'use client';

import { useEffect, useState } from 'react';
import { metrics as metricsApi } from '@/lib/api';
import type { Metrics } from '@/types';
import { Clock, Repeat, Brain, Shield, Save, AlertTriangle, CheckCircle, TrendingUp } from 'lucide-react';

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { metricsApi.get().then(setMetrics).catch(() => {}).finally(() => setLoading(false)); }, []);

  if (loading) return <div className="p-6 text-fg-400">Loading metrics...</div>;
  if (!metrics) return <div className="p-6 text-fg-400">No metrics available. Run some executions first.</div>;

  const cards = [
    { label: 'Cycle Time', value: `${metrics.headline.cycleTimeHours}h`, icon: Clock, color: 'text-brand-cyan' },
    { label: 'Rework Rate', value: `${metrics.headline.reworkRate}%`, icon: Repeat, color: 'text-brand-amber' },
    { label: 'Knowledge Reuse', value: `${metrics.headline.knowledgeReuseRate}%`, icon: Brain, color: 'text-[#a594ff]' },
    { label: 'Compliance', value: `${metrics.headline.complianceScore}%`, icon: Shield, color: 'text-brand-cyan' },
    { label: 'Hours Saved', value: metrics.headline.hoursSaved, icon: Save, color: 'text-brand-cyan' },
    { label: 'Violations Prevented', value: metrics.headline.violationsPrevented, icon: AlertTriangle, color: 'text-brand-amber' },
    { label: 'Audit Readiness', value: `${metrics.headline.auditReadiness}%`, icon: CheckCircle, color: 'text-brand-cyan' },
    { label: 'Acceptance Rate', value: `${metrics.headline.acceptanceRate}%`, icon: TrendingUp, color: 'text-brand-cyan' },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-white">Metrics</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div key={card.label} className="panel panel-hover p-4">
            <div className="flex items-center gap-2 mb-2">
              <card.icon className={`w-4 h-4 ${card.color}`} />
              <span className="text-[10px] font-bold text-fg-500 uppercase tracking-wider">{card.label}</span>
            </div>
            <div className={`text-2xl font-bold ${card.color}`}>{card.value}</div>
          </div>
        ))}
      </div>
      <div className="panel p-5">
        <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-4">Operational Details</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div><span className="text-fg-500">Total Executions:</span> <span className="text-fg-100 font-semibold">{metrics.operational.totalExecutions}</span></div>
          <div><span className="text-fg-500">Total Artifacts:</span> <span className="text-fg-100 font-semibold">{metrics.operational.totalArtifacts}</span></div>
          <div><span className="text-fg-500">Total Evidence:</span> <span className="text-fg-100 font-semibold">{metrics.operational.totalEvidence}</span></div>
          <div><span className="text-fg-500">Blocked:</span> <span className="text-fg-100 font-semibold">{metrics.operational.blockedExecutions}</span></div>
        </div>
      </div>
      <div className="panel p-5">
        <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-4">Knowledge Base</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div><span className="text-fg-500">Learning Objects:</span> <span className="text-fg-100 font-semibold">{metrics.knowledge.learningObjects}</span></div>
          <div><span className="text-fg-500">Patterns:</span> <span className="text-fg-100 font-semibold">{metrics.knowledge.patterns}</span></div>
          <div><span className="text-fg-500">Policies:</span> <span className="text-fg-100 font-semibold">{metrics.knowledge.policies}</span></div>
          <div><span className="text-fg-500">Constitutional:</span> <span className="text-fg-100 font-semibold">{metrics.knowledge.constitutionalPolicies}</span></div>
        </div>
      </div>
    </div>
  );
}
