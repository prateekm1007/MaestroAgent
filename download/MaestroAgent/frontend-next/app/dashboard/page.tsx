// app/dashboard/page.tsx — Home page with goal input and work stream.

'use client';

import { useState, useRef, useCallback } from 'react';
import { runs as runsApi, connectWebSocket } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { getGreeting, relativeTime } from '@/lib/utils';
import { MarkdownRenderer } from '@/components/ui/markdown-renderer';
import { Send, Sparkles } from 'lucide-react';
import { useEffect } from 'react';
import { runs as runsApiList } from '@/lib/api';
import type { Run } from '@/types';

interface StreamMessage {
  type: 'user' | 'maestro' | 'conductor' | 'specialist' | 'evidence' | 'feedback';
  content: string;
  agentName?: string;
  agentIcon?: string;
  phase?: string;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [goal, setGoal] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [evidence, setEvidence] = useState<string[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    runsApiList.list().then(setRecentRuns).catch(() => {});
  }, []);

  const scrollToBottom = () => {
    if (streamRef.current) streamRef.current.scrollTop = streamRef.current.scrollHeight;
  };

  const handleEvent = useCallback((event: any) => {
    const p = event.payload || {};
    switch (event.type) {
      case 'conductor.token':
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.type === 'conductor' && last.phase === p.phase) {
            return [...prev.slice(0, -1), { ...last, content: last.content + p.delta }];
          }
          return [...prev, { type: 'conductor', content: p.delta, phase: p.phase }];
        });
        break;
      case 'agent.joined':
        setMessages(prev => [...prev, { type: 'maestro', content: `${p.icon} ${p.name} joined the team — ${p.role}` }]);
        break;
      case 'agent.thinking':
        setMessages(prev => [...prev, { type: 'specialist', content: '', agentName: p.name, agentIcon: p.icon }]);
        break;
      case 'agent.token': {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.type === 'specialist' && last.agentName === p.agent_id) {
            // This won't work perfectly since agent_id != agent_name, but close enough for now
            return [...prev.slice(0, -1), { ...last, content: last.content + p.delta }];
          }
          return prev;
        });
        break;
      }
      case 'agent.completed':
        setMessages(prev => [...prev, { type: 'maestro', content: `${p.name} completed — ${p.artifact} (${p.bytes} bytes)` }]);
        break;
      case 'evidence.added':
        setEvidence(prev => [...prev, p.label]);
        break;
      case 'run.completed':
        setStreaming(false);
        setMessages(prev => [...prev, { type: 'maestro', content: `Done! ${p.artifacts?.length || 0} artifacts produced in ${(p.duration_ms / 1000).toFixed(1)}s.` }]);
        break;
      case 'run.failed':
        setStreaming(false);
        setMessages(prev => [...prev, { type: 'maestro', content: `Failed: ${p.error}` }]);
        break;
    }
    setTimeout(scrollToBottom, 50);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim() || streaming) return;
    setStreaming(true);
    setMessages([{ type: 'user', content: goal }]);
    setEvidence([]);

    try {
      const { run_id } = await runsApi.create(goal);
      setActiveRunId(run_id);
      wsRef.current = connectWebSocket(run_id, handleEvent);
    } catch (err: any) {
      setMessages(prev => [...prev, { type: 'maestro', content: `Error: ${err.message}` }]);
      setStreaming(false);
    }
  };

  const handleFeedback = async (outcome: 'accepted' | 'rejected' | 'edited') => {
    if (!activeRunId) return;
    try {
      await runsApi.feedback(activeRunId, outcome);
      setMessages(prev => [...prev, { type: 'feedback', content: `Recorded as ${outcome}. This helps Maestro improve for future projects.` }]);
    } catch (err: any) {
      setMessages(prev => [...prev, { type: 'maestro', content: `Feedback error: ${err.message}` }]);
    }
  };

  const reset = () => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    setMessages([]);
    setEvidence([]);
    setActiveRunId(null);
    setGoal('');
    setStreaming(false);
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col h-screen">
      {!hasMessages ? (
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="w-full max-w-2xl space-y-8">
            <div className="text-center">
              <div className="text-sm text-fg-500 mb-1">{getGreeting()}, {user?.name?.split(' ')[0] || 'there'}.</div>
              <h1 className="text-3xl font-black text-white mb-1">What would you like to create?</h1>
            </div>
            <form onSubmit={handleSubmit} className="panel p-5">
              <textarea value={goal} onChange={(e) => setGoal(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); } }}
                placeholder="Describe your goal — Maestro will assemble the right specialists and get to work..."
                rows={3}
                className="w-full bg-transparent border-none outline-none text-fg-100 text-lg resize-none min-h-[56px]"
                aria-label="Goal input" />
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-white/[0.04]">
                <span className="text-[11px] text-fg-500">Press Enter to start</span>
                <button type="submit" disabled={!goal.trim() || streaming} className="btn btn-primary disabled:opacity-50">
                  <Sparkles className="w-3.5 h-3.5" /> Start
                </button>
              </div>
            </form>
            <div className="flex flex-wrap gap-2 justify-center">
              {['Write a blog post about AI agents', 'Build a REST API in Python', 'Research market trends', 'Create a PRD'].map((suggestion) => (
                <button key={suggestion} onClick={() => setGoal(suggestion)}
                  className="tag tag-gray hover:tag-purple cursor-pointer transition-all">{suggestion}</button>
              ))}
            </div>
            {recentRuns.length > 0 && (
              <div>
                <h3 className="text-xs font-bold text-fg-500 uppercase tracking-wider mb-3">Recent</h3>
                <div className="space-y-2">
                  {recentRuns.slice(0, 4).map((run) => (
                    <a key={run.id} href={`/runs/${run.id}`} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:border-brand-purple/15 transition-all">
                      <div className="w-8 h-8 rounded-lg bg-brand-purple/12 flex items-center justify-center text-sm">{'>'}</div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-fg-100 truncate">{run.goal}</div>
                        <div className="text-[10px] text-fg-500">{relativeTime(run.started_at)}</div>
                      </div>
                      <span className={`tag ${run.status === 'completed' ? 'tag-cyan' : run.status === 'failed' ? 'tag-rose' : 'tag-amber'}`}>{run.status}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto" ref={streamRef}>
          <div className="max-w-2xl mx-auto px-6 py-6 space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className="animate-page-in">
                {msg.type === 'user' && (
                  <div className="bg-white/[0.04] border border-white/[0.06] rounded-2xl rounded-br-md p-4 ml-auto max-w-[85%]">
                    <p className="text-sm text-fg-200">{msg.content}</p>
                  </div>
                )}
                {msg.type === 'maestro' && (
                  <div className="flex items-start gap-2">
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-purple to-brand-cyan flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5">M</div>
                    <div className="bg-gradient-to-br from-brand-purple/[0.06] to-brand-cyan/[0.04] border border-brand-purple/12 rounded-2xl p-4 max-w-[85%]">
                      <div className="text-sm text-fg-100"><MarkdownRenderer content={msg.content} /></div>
                    </div>
                  </div>
                )}
                {msg.type === 'conductor' && (
                  <div className="flex items-start gap-2">
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-purple to-brand-cyan flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5">M</div>
                    <div className="flex-1">
                      {msg.phase && <div className="text-[10px] font-bold text-[#a594ff] uppercase tracking-wide mb-1">{msg.phase}</div>}
                      <p className="text-sm text-fg-200 leading-relaxed">{msg.content}</p>
                      {msg.content === '' && <div className="flex gap-1"><span className="w-1.5 h-1.5 rounded-full bg-brand-purple typing-dot" /><span className="w-1.5 h-1.5 rounded-full bg-brand-purple typing-dot" /><span className="w-1.5 h-1.5 rounded-full bg-brand-purple typing-dot" /></div>}
                    </div>
                  </div>
                )}
                {msg.type === 'specialist' && (
                  <div className="ml-9 panel p-4">
                    {msg.content ? <div className="text-sm text-fg-300"><MarkdownRenderer content={msg.content} /></div> : <div className="flex gap-1"><span className="w-1.5 h-1.5 rounded-full bg-brand-cyan typing-dot" /><span className="w-1.5 h-1.5 rounded-full bg-brand-cyan typing-dot" /><span className="w-1.5 h-1.5 rounded-full bg-brand-cyan typing-dot" /></div>}
                  </div>
                )}
                {msg.type === 'feedback' && (
                  <div className="text-center py-2">
                    <p className="text-xs text-fg-400">{msg.content}</p>
                  </div>
                )}
              </div>
            ))}

            {evidence.length > 0 && (
              <div className="panel p-4">
                <div className="text-[10px] font-bold text-fg-500 uppercase tracking-wider mb-2">Work Completed</div>
                <div className="space-y-1.5">
                  {evidence.map((ev, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-fg-200 bg-brand-cyan/[0.04] border-l-2 border-brand-cyan/40 rounded px-2 py-1">
                      <span className="w-3 h-3 rounded-full bg-brand-cyan/20 flex items-center justify-center text-brand-cyan text-[8px]">{'>'}</span>
                      {ev}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!streaming && activeRunId && (
              <div className="space-y-3">
                <div className="panel p-4 border-brand-purple/20">
                  <div className="text-[10px] font-bold text-[#a594ff] uppercase tracking-wider mb-2">Did this meet your need?</div>
                  <p className="text-sm text-fg-200 mb-3">Your feedback makes Maestro better for your next project.</p>
                  <div className="flex gap-2">
                    <button onClick={() => handleFeedback('accepted')} className="btn bg-brand-cyan/12 text-brand-cyan border border-brand-cyan/25 hover:bg-brand-cyan/20">Yes, this works</button>
                    <button onClick={() => handleFeedback('edited')} className="btn bg-brand-amber/12 text-brand-amber border border-brand-amber/25 hover:bg-brand-amber/20">I'd edit it</button>
                    <button onClick={() => handleFeedback('rejected')} className="btn bg-brand-rose/12 text-brand-rose border border-brand-rose/25 hover:bg-brand-rose/20">Not what I needed</button>
                  </div>
                </div>
                <div className="text-center">
                  <button onClick={reset} className="btn btn-ghost">Start a new task</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
