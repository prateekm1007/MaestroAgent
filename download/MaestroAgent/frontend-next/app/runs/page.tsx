// app/runs/page.tsx — Runs list page.

'use client';

import { useEffect, useState } from 'react';
import { runs as runsApi } from '@/lib/api';
import { relativeTime, formatDuration } from '@/lib/utils';
import type { Run } from '@/types';
import Link from 'next/link';

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { runsApi.list().then(setRuns).catch(() => {}).finally(() => setLoading(false)); }, []);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Runs</h1>
      {loading ? <p className="text-fg-400">Loading...</p> : runs.length === 0 ? <p className="text-fg-400">No runs yet. Start one from the dashboard.</p> : (
        <div className="panel">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-[10px] font-bold text-fg-500 uppercase tracking-wider">
                <th className="text-left px-4 py-3">Goal</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Duration</th>
                <th className="text-left px-4 py-3">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-3"><Link href={`/runs/${run.id}`} className="text-fg-100 hover:text-brand-purple truncate block max-w-md">{run.goal}</Link></td>
                  <td className="px-4 py-3"><span className={`tag ${run.status === 'completed' ? 'tag-cyan' : run.status === 'failed' ? 'tag-rose' : 'tag-amber'}`}>{run.status}</span></td>
                  <td className="px-4 py-3 text-fg-400 font-mono text-xs">{run.duration_ms ? formatDuration(run.duration_ms) : '-'}</td>
                  <td className="px-4 py-3 text-fg-400 text-xs">{relativeTime(run.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
