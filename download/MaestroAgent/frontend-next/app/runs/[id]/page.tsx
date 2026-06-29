// app/runs/[id]/page.tsx — Run detail page with live event stream.

'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { runs as runsApi, connectWebSocket } from '@/lib/api';
import { renderMarkdown, formatBytes, relativeTime } from '@/lib/utils';
import type { Run, RunEvent } from '@/types';
import { Download, AlertCircle } from 'lucide-react';

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    runsApi.get(runId).then(setRun).catch(() => {});
    runsApi.getEvents(runId).then(setEvents).catch(() => {});
    runsApi.getArtifacts(runId).then(setArtifacts).catch(() => {});

    if (run?.status === 'running') {
      wsRef.current = connectWebSocket(runId, (event) => {
        setEvents(prev => [...prev, event]);
      });
    }

    return () => { wsRef.current?.close(); };
  }, [runId, run?.status]);

  const conductorEvents = events.filter(e => e.type.startsWith('conductor'));
  const agentEvents = events.filter(e => e.type.startsWith('agent'));
  const systemEvents = events.filter(e => !e.type.startsWith('conductor') && !e.type.startsWith('agent'));

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <div className="text-[10px] font-bold text-fg-500 uppercase tracking-wider mb-1">Run Detail</div>
        <h1 className="text-xl font-bold text-white">{run?.goal || 'Loading...'}</h1>
        <div className="flex items-center gap-3 mt-2 text-xs text-fg-400">
          <span className={`tag ${run?.status === 'completed' ? 'tag-cyan' : run?.status === 'failed' ? 'tag-rose' : 'tag-amber'}`}>{run?.status}</span>
          <span>{run?.started_at && relativeTime(run.started_at)}</span>
          {run?.duration_ms && <span>{(run.duration_ms / 1000).toFixed(1)}s</span>}
          {run?.avg_confidence && <span className="text-brand-cyan">{run.avg_confidence}% confidence</span>}
        </div>
      </div>

      {run?.error && (
        <div className="panel p-4 border-brand-rose/20 flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-brand-rose flex-shrink-0 mt-0.5" />
          <div><div className="text-xs font-bold text-brand-rose uppercase tracking-wide">Error</div><p className="text-sm text-fg-300 mt-1">{run.error}</p></div>
        </div>
      )}

      {artifacts.length > 0 && (
        <div>
          <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Deliverables</h2>
          <div className="space-y-2">
            {artifacts.map((a) => (
              <div key={a.id} className={`panel p-4 flex items-center gap-3 ${a.is_final ? 'border-brand-cyan/30' : ''}`}>
                <div className="w-9 h-9 rounded-lg bg-brand-cyan/12 text-brand-cyan flex items-center justify-center text-[9px] font-bold font-mono">{a.filename.split('.').pop()?.toUpperCase()}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-fg-100 font-mono">{a.filename}</div>
                  <div className="text-[10px] text-fg-500">{a.agent_name} - {formatBytes(a.bytes)}{a.is_final ? ' - Final Deliverable' : ''}</div>
                </div>
                <a href={runsApi.artifactUrl(runId, a.filename)} target="_blank" rel="noopener" className="btn btn-ghost"><Download className="w-3 h-3" />Download</a>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Event Stream ({events.length})</h2>
        <div className="panel p-4 max-h-96 overflow-y-auto space-y-1 font-mono text-[11px]">
          {events.map((ev, i) => (
            <div key={i} className="flex gap-2 items-start py-0.5">
              <span className="text-fg-500 w-20 flex-shrink-0">{new Date(ev.ts).toLocaleTimeString()}</span>
              <span className={`tag ${ev.type.startsWith('conductor') ? 'tag-purple' : ev.type.startsWith('agent') ? 'tag-cyan' : ev.type.startsWith('run') ? 'tag-amber' : 'tag-gray'}`}>{ev.type}</span>
              <span className="text-fg-400 truncate">{JSON.stringify(ev.payload).slice(0, 120)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
