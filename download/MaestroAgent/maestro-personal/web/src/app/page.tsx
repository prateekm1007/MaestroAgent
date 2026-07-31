'use client'

import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Sun, Search, Calendar, Zap, Unplug, Mail, MessageSquare, FileText, RefreshCw, CheckCircle2, Plus, Send, Loader2, LogOut, Sparkles, PenLine, AlertTriangle, Clock, Lightbulb } from 'lucide-react'
import { maestroApi, getToken, setToken, clearToken } from '@/lib/maestro-api'
import { Login } from '@/components/maestro/Login'
import { DraftApprovalModal, type DraftWithMeta } from '@/components/maestro/DraftApprovalModal'
import ClickableCard from '@/components/maestro/ClickableCard'
import { calculateImportance, getLayoutMode, getConfidenceStyle } from '@/lib/importance'
import { TheOne } from '@/components/maestro/TheOne'
import { WhisperView } from '@/components/maestro/WhisperView'
import { WhisperPostIt } from '@/components/maestro/WhisperPostIt'
import { CommitmentsView } from '@/components/maestro/CommitmentsView'
import { CorrectionButton } from '@/components/maestro/CorrectionButton'
import { Connectors } from '@/components/maestro/Connectors'

function formatRelativeTime(iso: string): string {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hr ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`;
  return new Date(iso).toLocaleDateString();
}

type Tab = 'today' | 'ask' | 'commitments' | 'whisper' | 'connectors'

const API_BASE = typeof window !== 'undefined'
  ? (window.location.origin === 'https://web-production-d5c26.up.railway.app'
    ? 'https://maestroagent-production.up.railway.app'
    : 'http://localhost:8766')
  : 'https://maestroagent-production.up.railway.app'

export default function Home() {
  const [authed, setAuthed] = useState(false)
  const [checkingAuth, setCheckingAuth] = useState(true)
  const [tab, setTab] = useState<Tab>('today')

  // Draft modal state (shared across Today, Whisper, Connectors)
  const [draftForReview, setDraftForReview] = useState<DraftWithMeta | null>(null)
  const [draftResolving, setDraftResolving] = useState(false)
  const [draftBusy, setDraftBusy] = useState(false)

  useEffect(() => {
    setAuthed(!!getToken())
    setCheckingAuth(false)
    // Phase 2.8 safety: if checkingAuth somehow stays true for >5s
    // (e.g. JS error in useEffect), force it to false so the user
    // sees the login screen instead of an infinite spinner.
    const timeout = setTimeout(() => setCheckingAuth(false), 5000)
    return () => clearTimeout(timeout)
  }, [])

  // Generate a draft for an entity — opens the shared modal
  const handleGenerateDraft = async (entity: string) => {
    if (!entity) return
    setDraftBusy(true)
    try {
      const { data, live } = await maestroApi.generateAutoDraft('gmail', entity)
      if (live && data) {
        setDraftForReview(data as DraftWithMeta)
      } else {
        alert('Could not generate draft. Make sure Gmail is connected.')
      }
    } catch {
      alert('Draft generation failed. Please try again.')
    } finally {
      setDraftBusy(false)
    }
  }

  // Resolve draft — approve / deny / use_draft
  // F-35 fix (auditor v18): surface send failures — never close modal on
  // send_failed. The prior code closed the modal regardless of the result,
  // so the user believed the email was sent when it wasn't.
  const handleResolveDraft = async (draft: DraftWithMeta, resolution: 'approve' | 'deny' | 'use_draft') => {
    setDraftResolving(true)
    try {
      const { data, live } = await maestroApi.resolveDraft(draft.draft_id, resolution)
      if (!live) {
        alert('Backend unreachable. Could not resolve draft.')
        return
      }

      if (resolution === 'approve') {
        const status = data?.status || ''
        const sendError = data?.send_error || 'Unknown error'
        const sentMessageId = data?.sent_message_id || ''

        if (status === 'send_failed') {
          // Do NOT close the modal
          alert(`Send failed: ${sendError}. Check that Gmail is connected.`)
          // Fallback: log mailto URL to console
          if (draft.recipient) {
            const subject = encodeURIComponent(draft.subject || '')
            const body = encodeURIComponent(draft.body || '')
            console.warn(
              `Send failed. Use this mailto link: mailto:${draft.recipient}?subject=${subject}&body=${body}`
            )
          }
          return  // Keep modal open so user can retry or copy
        } else if (status === 'approved') {
          if (sentMessageId) {
            alert(`Sent. Message ID: ${sentMessageId}`)
          } else {
            alert('Sent (no message ID returned)')
          }
          setDraftForReview(null)
        } else {
          // Unexpected status
          alert(`Unexpected response. Status: ${status}`)
        }
      } else if (resolution === 'use_draft') {
        try {
          await navigator.clipboard?.writeText(draft.body || '')
        } catch { /* clipboard may be blocked */ }
        if (draft.recipient) {
          const subject = encodeURIComponent(draft.subject || '')
          const body = encodeURIComponent(draft.body || '')
          window.open(`mailto:${draft.recipient}?subject=${subject}&body=${body}`, '_blank')
        }
        alert('Opened in mail app. Body copied to clipboard as backup.')
        setDraftForReview(null)
      } else {
        alert('Discarded')
        setDraftForReview(null)
      }
    } catch (e: any) {
      const msg = e?.message || String(e)
      alert(`Failed to resolve draft: ${msg}`)
    } finally {
      setDraftResolving(false)
    }
  }

  if (checkingAuth) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
      </div>
    )
  }

  if (!authed) {
    return <Login onLoggedIn={() => setAuthed(true)} />
  }

  const navItems: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'today', label: 'Today', icon: <Sun className="h-4 w-4" /> },
    { id: 'ask', label: 'Ask', icon: <Search className="h-4 w-4" /> },
    { id: 'commitments', label: 'Commitments', icon: <Calendar className="h-4 w-4" /> },
    { id: 'whisper', label: 'Whisper', icon: <Zap className="h-4 w-4" /> },
    { id: 'connectors', label: 'Connectors', icon: <Unplug className="h-4 w-4" /> },
  ]

  const handleLogout = () => {
    clearToken()
    setAuthed(false)
  }

  return (
    <div className="min-h-screen flex bg-white">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-gray-100">
        <div className="p-5 flex items-center gap-3">
          <div className="h-7 w-7 rounded-md bg-gray-900 flex items-center justify-center">
            <span className="text-white text-xs font-bold">M</span>
          </div>
          <span className="font-semibold text-sm tracking-tight text-gray-900">Maestro</span>
        </div>
        <nav className="flex-1 px-3 py-2 space-y-1" aria-label="Main">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setTab(item.id)}
              className={cn('flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm transition-colors',
                tab === item.id ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-400 hover:text-gray-700 hover:bg-gray-50')}>
              {item.icon} {item.label}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-gray-100">
          <button onClick={handleLogout} className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-gray-700 hover:bg-gray-50 transition-colors">
            <LogOut className="h-4 w-4" /> Log out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="lg:hidden sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-gray-100">
          <div className="flex items-center justify-between px-6 py-3">
            <span className="font-semibold text-sm tracking-tight text-gray-900">Maestro</span>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <button key={item.id} onClick={() => setTab(item.id)}
                  className={cn('p-1.5 rounded-lg', tab === item.id ? 'bg-gray-100 text-gray-900' : 'text-gray-400')}>
                  {item.icon}
                </button>
              ))}
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-2xl w-full mx-auto px-6 lg:px-10 py-8 lg:py-10 pb-24 lg:pb-10">
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -2 }} transition={{ duration: 0.2 }}>
              {tab === 'today' && <TodayView onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
              {tab === 'today' && <WhisperPostIt onDraft={handleGenerateDraft} />}
              {tab === 'ask' && <AskView />}
              {tab === 'commitments' && <CommitmentsViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
              {tab === 'whisper' && <WhisperViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
              {tab === 'connectors' && <Connectors />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-gray-100 bg-white/95 backdrop-blur-sm" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="grid grid-cols-5">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setTab(item.id)}
              className={cn('flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] font-medium min-h-[44px]',
                tab === item.id ? 'text-gray-900' : 'text-gray-400')}>
              {item.icon}<span className="truncate max-w-full px-1">{item.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Shared Draft Approval Modal — proven design from DraftApprovalModal.tsx */}
      <DraftApprovalModal
        draft={draftForReview}
        open={!!draftForReview}
        onOpenChange={(o) => { if (!o) setDraftForReview(null) }}
        onResolve={handleResolveDraft}
        resolving={draftResolving}
      />
    </div>
  )
}

// === TODAY — real API ===
function TodayView({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [loading, setLoading] = useState(true)
  const [theOne, setTheOne] = useState<any>(null)
  const [changes, setChanges] = useState<any[]>([])
  const [commitments, setCommitments] = useState<any[]>([])
  const [error, setError] = useState('')
  // Audit fix S1-1 (2026-07-31): track whether the headline call (the-moment)
  // was reachable. The prior code silently treated a timed-out/unreachable
  // backend as "no commitments need attention" — a false negative that
  // destroyed trust on every cold page load. Now we distinguish three states:
  //   loading=true              → spinner
  //   loading=false, live=false → "Still loading your day…" banner (not "you're clear")
  //   loading=false, live=true  → genuine "you're clear" or the actual moment
  const [momentLive, setMomentLive] = useState(false)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        // P18 fix: fetch commitments in TodayView too, so "What Changed"
        // items can be matched to commitment_ids for ClickableCard.
        const [moment, shifts, commits] = await Promise.all([
          maestroApi.getTheMoment(),
          maestroApi.getTheShifts(),
          maestroApi.getCommitments(),
        ])
        if (!alive) return
        // Audit fix S1-1: record liveness so we can distinguish "backend
        // unreachable" from "genuinely no commitments". The prior code
        // collapsed both into theOne=null → "You're clear today".
        setMomentLive(!!moment.live)
        if (moment.live && moment.data) setTheOne(moment.data)
        if (shifts.live && shifts.data) setChanges(shifts.data.the_shifts || shifts.data.secondary || [])
        if (commits.live && Array.isArray(commits.data)) setCommitments(commits.data)
        setLoading(false)
      } catch (e) {
        if (alive) { setError('Failed to load. Please try again.'); setLoading(false) }
      }
    })()
    return () => { alive = false }
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>
  if (error) return (
    <div className="space-y-4">
      {/* Phase 2.3: Stale/offline honesty — visible banner when backend unreachable */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2">
        <span className="text-amber-600 text-sm font-medium">⚠ Backend not connected</span>
        <span className="text-amber-500 text-xs">Data may be stale. {error}</span>
      </div>
      <div className="text-sm text-gray-400 py-8">Retry in a moment.</div>
    </div>
  )

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">{greeting}.</h1>
        <p className="text-gray-400 mt-2 text-base">
          {theOne
            ? 'You have one promise that needs attention.'
            : momentLive
              ? "You're clear today. No commitments need attention."
              : 'Still loading your day — your commitments will appear here shortly.'}
        </p>
      </div>
      {/* Audit fix S1-1 (2026-07-31): if the headline call didn't reach the
          backend (timeout or unreachable), show a visible banner instead of
          the false-negative "you're clear" message. This is the
          defense-in-depth layer on top of the raised timeout + extended
          cache TTL. */}
      {!momentLive && !theOne && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2">
          <span className="text-amber-600 text-sm font-medium">⚠ Still loading</span>
          <span className="text-amber-500 text-xs">
            The backend is taking longer than usual to build your dashboard. Refresh in a moment.
          </span>
        </div>
      )}

      {theOne && theOne.commitment && (
        <div>
          <TheOne
            commitment={{
              id: theOne.commitment.signal_id || 'the-one',
              entity: theOne.commitment.entity || '',
              text: theOne.commitment.text || theOne.commitment.action || '',
              dueDate: theOne.commitment.deadline || new Date().toISOString(),
              state: theOne.commitment.is_at_risk ? 'at_risk' : 'active',
              confidence: theOne.commitment.confidence ?? 0.5,
              importance: theOne.commitment.is_at_risk ? 'high' : 'medium',
              isBlocking: false,
              owner: 'user',
              source: { type: 'email', snippet: theOne.commitment.text || '', timestamp: theOne.commitment.created_at || '', sender: '' },
              createdAt: theOne.commitment.created_at || '',
            }}
            apiBase={API_BASE}
            token={getToken() || ''}
          />
          <button
            onClick={() => onDraft(theOne.commitment.entity)}
            disabled={draftBusy}
            className="mt-3 flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 px-4 py-2 rounded-lg bg-white border border-gray-200 hover:border-gray-300 transition-colors disabled:opacity-50"
          >
            {draftBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PenLine className="h-4 w-4" />}
            Draft Follow-up Email
          </button>
        </div>
      )}

      {changes.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">What Changed</p>
          <div className="space-y-3">
            {changes.slice(0, 5).map((c, i) => {
              const match = commitments.find((cm: any) =>
                cm.text && c.text && cm.text === c.text
              );
              const commitmentId = match?.signal_id || `change-${i}`;
              return (
                <ClickableCard
                  key={i}
                  commitment={{
                    commitment_id: commitmentId,
                    entity: c.entity || 'Unknown',
                    text: c.text || c.action || 'Change detected',
                    state: 'active',
                    confidence: typeof c.confidence === 'number' ? c.confidence : 0.5,
                  }}
                  apiBase={API_BASE}
                  token={getToken() || ''}
                >
                  <div className="flex items-start gap-3 hover:bg-gray-50 transition-colors p-2 rounded-lg">
                    <div className={cn('flex-shrink-0 mt-1 h-1.5 w-1.5 rounded-full',
                      c.type === 'new' ? 'bg-blue-400' : c.is_meaningful ? 'bg-amber-400' : 'bg-gray-300')} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-700 leading-relaxed">{c.text || c.action || JSON.stringify(c)}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{c.entity || ''}</p>
                    </div>
                  </div>
                </ClickableCard>
              );
            })}
          </div>
        </div>
      )}

      {/* v21: Show active commitments list on Today page — user expects to see
          their commitments, not just "the one" that needs attention. */}
      {commitments.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-medium uppercase tracking-wider text-gray-400">Your Active Commitments</p>
            <span className="text-xs text-gray-400">{commitments.length} total</span>
          </div>
          <div className="space-y-2">
            {commitments.slice(0, 10).map((c: any, i: number) => (
              <ClickableCard
                key={c.signal_id || i}
                commitment={{
                  commitment_id: c.signal_id || `commitment-${i}`,
                  entity: c.entity || 'Unknown',
                  text: c.text || c.action || '',
                  state: c.is_at_risk ? 'at_risk' : 'active',
                  confidence: typeof c.confidence === 'number' ? c.confidence : 0.5,
                }}
                apiBase={API_BASE}
                token={getToken() || ''}
              >
                <div className="flex items-start gap-3 hover:bg-gray-50 transition-colors p-3 rounded-lg border border-gray-100">
                  <div className={cn('flex-shrink-0 mt-1 h-2 w-2 rounded-full',
                    c.is_at_risk ? 'bg-red-400' : c.deadline ? 'bg-amber-400' : 'bg-emerald-400')} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 leading-snug">{c.text || c.action || ''}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <p className="text-xs text-gray-400">{c.entity || ''}</p>
                      {c.deadline && (
                        <p className="text-xs text-amber-500">{new Date(c.deadline).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</p>
                      )}
                      {c.is_at_risk && (
                        <span className="text-[10px] font-medium text-red-500 uppercase tracking-wide">at risk</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); onDraft(c.entity) }}
                    disabled={draftBusy}
                    className="flex-shrink-0 text-xs text-gray-400 hover:text-gray-700 disabled:opacity-50 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
                    title="Draft follow-up"
                  >
                    <PenLine className="h-3.5 w-3.5" />
                  </button>
                </div>
              </ClickableCard>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// === ASK — real API ===
function AskView() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [showEvidence, setShowEvidence] = useState(false)

  const handleAsk = async (q: string) => {
    if (!q.trim()) return
    setLoading(true); setAnswer(null)
    try {
      // Phase 4 fix (auditor v17): try streaming first for sub-2s perceived latency.
      // Falls back to regular /api/ask if streaming fails.
      const API_BASE_LOCAL = typeof window !== 'undefined'
        ? (window.location.origin === 'https://web-production-d5c26.up.railway.app'
          ? 'https://maestroagent-production.up.railway.app'
          : 'http://localhost:8766')
        : 'https://maestroagent-production.up.railway.app'
      const _token = getToken()
      let streamDone = false
      try {
        const streamRes = await fetch(`${API_BASE_LOCAL}/api/ask/stream`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${_token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ query: q }),
        })
        if (streamRes.ok && streamRes.body) {
          const reader = streamRes.body.getReader()
          const decoder = new TextDecoder()
          let chunks = ''
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const text = decoder.decode(value, { stream: true })
            // Parse SSE data lines
            for (const line of text.split('\n')) {
              if (line.startsWith('data: ')) {
                const payload = line.slice(6).trim()
                if (payload === '[DONE]') { streamDone = true; break }
                try {
                  const parsed = JSON.parse(payload)
                  if (parsed.chunk) chunks += parsed.chunk
                  if (parsed.answer) { chunks = parsed.answer; streamDone = true; break }
                } catch {}
              }
            }
            if (streamDone) break
            // Update answer progressively for perceived latency
            if (chunks) {
              setAnswer({ answer: chunks, confidence: 0.5, evidence_refs: [], _streaming: true })
            }
          }
          if (chunks) {
            // Final fetch to get full response with evidence
            const { data, live } = await maestroApi.ask(q)
            if (live) setAnswer(data)
            else setAnswer({ answer: chunks, confidence: 0.5, evidence_refs: [] })
            return
          }
        }
      } catch (streamErr) {
        // Streaming failed — fall through to regular ask
      }
      // Fallback: regular /api/ask
      const { data, live } = await maestroApi.ask(q)
      if (live) setAnswer(data)
      else setAnswer({ answer: 'Backend not connected.', confidence: 0, evidence_refs: [] })
    } catch { setAnswer({ answer: 'Request failed. Please try again.', confidence: 0, evidence_refs: [] }) }
    finally { setLoading(false) }
  }

  const suggestions = ['What did I promise Maria?', 'What\'s at risk today?', 'What did I commit to this week?']

  return (
    <div className="flex flex-col items-center w-full">
      <div className="w-full max-w-2xl">
        <form onSubmit={(e) => { e.preventDefault(); handleAsk(query) }} className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about your commitments..."
            className="w-full pl-11 pr-4 py-3.5 bg-white rounded-xl border border-gray-200 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400 text-sm" />
        </form>

        {!answer && !loading && (
          <div className="flex flex-wrap gap-2 mt-4">
            {suggestions.map((s) => (
              <button key={s} onClick={() => { setQuery(s); handleAsk(s) }}
                className="px-3 py-1.5 text-sm text-gray-500 bg-gray-50 hover:bg-gray-100 rounded-full transition-colors">{s}</button>
            ))}
          </div>
        )}

        {loading && <div className="mt-8 flex items-center gap-2 text-gray-400"><Loader2 className="h-4 w-4 animate-spin" /><span className="text-sm">Searching your commitments...</span></div>}

        <AnimatePresence>
          {answer && !loading && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-8">
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ background: (answer.confidence || 0) >= 0.7 ? '#059669' : '#6B7280' }} />
                  <span className="text-xs text-gray-400 tabular-nums">{Math.round((answer.confidence || 0) * 100)}% confidence</span>
                </div>
                <p className="text-lg leading-relaxed tracking-tight" style={{ color: (answer.confidence || 0) >= 0.7 ? '#1A1A1A' : '#6B7280' }}>
                  {answer.answer || 'No answer available.'}
                </p>
              </div>

              {answer.evidence_refs && answer.evidence_refs.length > 0 && (
                <div className="mt-4">
                  <button onClick={() => setShowEvidence(!showEvidence)}
                    className="flex items-center gap-1 text-sm font-medium text-gray-500 hover:text-gray-700 mb-2">
                    Evidence ({answer.evidence_refs.length})
                  </button>
                  <AnimatePresence>
                    {showEvidence && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="overflow-hidden">
                        <div className="space-y-4">
                          {answer.evidence_refs.map((ev: any, i: number) => (
                            <div key={i} className="pl-4 border-l-2 rounded-r-lg" style={{ borderColor: '#2563EB', background: '#F9FAFB' }}>
                              <div className="p-3">
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex-1">
                                    <span className="text-xs text-gray-400">{ev.source_type || ev.source || 'signal'}</span>
                                    <p className="text-sm italic text-gray-700 leading-relaxed mt-1">"{ev.text || ev.evidence_quote || ''}"</p>
                                  </div>
                                  {/* Phase 2.6: Correction UI — user can correct a wrong commitment */}
                                  {ev.signal_id && (
                                    <CorrectionButton
                                      signalId={ev.signal_id}
                                      apiBase={API_BASE}
                                      token={getToken() || ''}
                                      onCorrected={() => {
                                        // Refresh the answer after correction
                                        handleAsk(query)
                                      }}
                                    />
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {answer.intelligence_source && (
                <p className="text-xs text-gray-400 mt-4">Source: {answer.intelligence_source}</p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// === COMMITMENTS — real API ===
function CommitmentsViewReal({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [loading, setLoading] = useState(true)
  const [commitments, setCommitments] = useState<any[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const { data, live } = await maestroApi.getCommitments()
        if (!alive) return
        if (live && Array.isArray(data)) setCommitments(data)
        setLoading(false)
      } catch { if (alive) { setError('Failed to load commitments.'); setLoading(false) } }
    })()
    return () => { alive = false }
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>
  if (error) return <div className="text-sm text-red-500 py-8">{error}</div>
  if (!commitments.length) return (
    <div className="text-center py-16">
      <p className="text-lg text-gray-400">No active commitments.</p>
      <p className="text-sm text-gray-400 mt-1">Connect a tool or create a signal to start tracking.</p>
    </div>
  )

  const sorted = [...commitments].sort((a, b) => (b.is_at_risk ? 1 : 0) - (a.is_at_risk ? 1 : 0))
  const theOne = sorted[0]
  const rest = sorted.slice(1)

  return (
    <div className="max-w-2xl mx-auto">
      {theOne && (
        <div className="mb-8">
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">The One</p>

            <TheOne
              commitment={{
                id: theOne.signal_id || 'c1', entity: theOne.entity || '', text: theOne.text || theOne.action || '',
                dueDate: theOne.deadline || new Date().toISOString(), state: theOne.is_at_risk ? 'at_risk' : 'active',
                confidence: theOne.confidence ?? 0.5, importance: theOne.is_at_risk ? 'high' : 'medium', isBlocking: false,
                owner: 'user', source: { type: 'email', snippet: theOne.text || '', timestamp: '', sender: '' }, createdAt: '',
              }}
              apiBase={API_BASE}
              token={getToken() || ''}
            />

        </div>
      )}
      {rest.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">All Active ({rest.length})</p>
          <div className="space-y-2">
            {rest.map((c, i) => (
              <ClickableCard
                key={c.signal_id || i}
                commitment={{
                  commitment_id: c.signal_id || `c-${i}`,
                  entity: c.entity || '',
                  text: c.text || c.action || '',
                  state: c.is_at_risk ? 'at_risk' : 'active',
                  confidence: c.confidence ?? 0.5,
                  deadline_text: c.deadline,
                  source_signal_id: c.signal_id
                }}
                apiBase={API_BASE}
                token={getToken() || ''}
              >
                <div className="flex items-center gap-3 py-3 px-4 bg-white rounded-lg border border-gray-100">
                  <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: (c.confidence || 0.5) >= 0.7 ? '#059669' : '#D97706' }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-700 truncate">{c.text || c.action}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{c.entity}</p>
                  </div>
                  {c.is_at_risk && <span className="text-xs text-red-500 font-medium">At risk</span>}
                </div>
              </ClickableCard>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// === WHISPER — real API (elite UI, matches Today page design) ===
function WhisperViewReal({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [loading, setLoading] = useState(true)
  const [whispers, setWhispers] = useState<any[]>([])
  const [error, setError] = useState('')
  const [whisperLive, setWhisperLive] = useState(false)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const { data, live } = await maestroApi.getWhispers()
        if (!alive) return
        setWhisperLive(!!live)
        const list = Array.isArray(data) ? data : (data ? [data] : [])
        if (live) setWhispers(list)
        setLoading(false)
      } catch { if (alive) { setError('Failed to load whispers.'); setLoading(false) } }
    })()
    return () => { alive = false }
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>
  if (error) return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2">
        <span className="text-amber-600 text-sm font-medium">⚠ Failed to load</span>
        <span className="text-amber-500 text-xs">{error}</span>
      </div>
    </div>
  )

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  // Group whispers by priority for a cleaner layout
  const highPriority = whispers.filter(w => w.priority === 'high')
  const mediumPriority = whispers.filter(w => w.priority === 'medium' || !w.priority)
  const lowPriority = whispers.filter(w => w.priority === 'low')

  return (
    <div className="space-y-10">
      {/* Header — matches Today page's h1 + subtitle pattern */}
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Whispers.</h1>
        <p className="text-gray-400 mt-2 text-base">
          {whispers.length > 0
            ? `${whispers.length} ${whispers.length === 1 ? 'insight needs' : 'insights need'} your attention right now.`
            : whisperLive
              ? "You're all caught up. No proactive insights right now."
              : 'Still loading your whispers — they will appear here shortly.'}
        </p>
      </div>

      {/* Loading banner when backend is slow */}
      {!whisperLive && !whispers.length && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2">
          <span className="text-amber-600 text-sm font-medium">⚠ Still loading</span>
          <span className="text-amber-500 text-xs">
            The backend is taking longer than usual. Refresh in a moment.
          </span>
        </div>
      )}

      {/* Empty state — elegant, not just "All caught up" */}
      {whisperLive && whispers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-16 w-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
            <Zap className="h-7 w-7 text-gray-300" />
          </div>
          <p className="text-lg font-medium text-gray-900">All caught up.</p>
          <p className="text-sm text-gray-400 mt-1">No proactive insights right now. Maestro is monitoring your commitments in the background.</p>
        </div>
      )}

      {/* High priority whispers — full-width cards with red accent */}
      {highPriority.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">Needs Attention</p>
          <div className="space-y-3">
            {highPriority.map((w, i) => (
              <WhisperCardElite
                key={w.id || w.whisper_id || `h-${i}`}
                whisper={w}
                priority="high"
                onDraft={onDraft}
                draftBusy={draftBusy}
              />
            ))}
          </div>
        </div>
      )}

      {/* Medium priority whispers */}
      {mediumPriority.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">Worth Knowing</p>
          <div className="space-y-3">
            {mediumPriority.map((w, i) => (
              <WhisperCardElite
                key={w.id || w.whisper_id || `m-${i}`}
                whisper={w}
                priority="medium"
                onDraft={onDraft}
                draftBusy={draftBusy}
              />
            ))}
          </div>
        </div>
      )}

      {/* Low priority whispers — collapsed by default */}
      {lowPriority.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">FYI</p>
          <div className="space-y-3">
            {lowPriority.map((w, i) => (
              <WhisperCardElite
                key={w.id || w.whisper_id || `l-${i}`}
                whisper={w}
                priority="low"
                onDraft={onDraft}
                draftBusy={draftBusy}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Elite whisper card — clean, minimal, with priority-based accent colors
function WhisperCardElite({
  whisper,
  priority,
  onDraft,
  draftBusy,
}: {
  whisper: any
  priority: 'high' | 'medium' | 'low'
  onDraft: (entity: string) => void
  draftBusy: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const entity = whisper.entity || 'Insight'
  const title = whisper.title || whisper.text || whisper.message || 'Insight'
  const body = whisper.body || whisper.context || whisper.detail || ''
  const wType = whisper.type || 'routine'

  // Priority-based styling — subtle, not garish
  const accentColor = priority === 'high' ? 'bg-red-500' : priority === 'medium' ? 'bg-amber-400' : 'bg-gray-300'
  const typeIcon = wType === 'critical_signal' ? AlertTriangle : wType === 'meeting_prep' ? Calendar : wType === 'deadline_approaching' ? Calendar : wType === 'stale_commitment' ? Clock : Lightbulb
  const TypeIcon = typeIcon

  return (
    <ClickableCard
      commitment={{
        commitment_id: whisper.id || whisper.whisper_id || whisper.signal_id || `w-${entity}`,
        entity,
        text: body || title,
        state: 'active',
        confidence: whisper.probability ? whisper.probability / 100 : 0.5,
        source_signal_id: whisper.id || whisper.signal_id || '',
      }}
      apiBase={API_BASE}
      token={getToken() || ''}
    >
      <div className="p-5 rounded-2xl bg-white border border-gray-100 hover:border-gray-200 transition-colors">
        {/* Top row: accent bar + type icon + entity */}
        <div className="flex items-start gap-3">
          <div className={cn('w-1 self-stretch rounded-full', accentColor)} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <TypeIcon className={cn('h-4 w-4 shrink-0',
                priority === 'high' ? 'text-red-500' : priority === 'medium' ? 'text-amber-500' : 'text-gray-400')} />
              <span className="text-xs font-medium uppercase tracking-wide text-gray-400">{wType.replace(/_/g, ' ')}</span>
            </div>
            <h3 className="font-semibold text-sm text-gray-900 leading-snug">{title}</h3>
            {body && (
              <p className={cn('text-sm text-gray-500 mt-1', !expanded && 'line-clamp-2')}>
                {body}
              </p>
            )}
            {/* Expand toggle for long bodies */}
            {body && body.length > 120 && (
              <button
                onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
                className="text-xs font-medium text-gray-400 hover:text-gray-600 mt-1"
              >
                {expanded ? 'Show less' : 'Show more'}
              </button>
            )}
          </div>
        </div>
        {/* Action row */}
        <div className="flex items-center gap-2 mt-4 pl-4">
          {entity && entity !== 'Insight' && (
            <button
              onClick={(e) => { e.stopPropagation(); onDraft(entity) }}
              disabled={draftBusy}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 hover:border-gray-300 transition-colors disabled:opacity-50"
            >
              {draftBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PenLine className="h-3.5 w-3.5" />}
              Draft Follow-up
            </button>
          )}
          {whisper.suggested_actions?.length > 0 && whisper.suggested_actions.map((a: any, j: number) => (
            <button
              key={j}
              onClick={(e) => e.stopPropagation()}
              className="text-xs font-medium text-gray-600 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 hover:border-gray-300 transition-colors"
            >
              {a.label || a}
            </button>
          ))}
        </div>
      </div>
    </ClickableCard>
  )
}

