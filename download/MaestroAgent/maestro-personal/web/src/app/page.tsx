'use client'

import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils'
// Tufte: removed framer-motion (motion/AnimatePresence) — no decorative animations
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
      {/* Desktop sidebar — Tufte: hairline border, position-based active state */}
      <aside className="hidden lg:flex w-56 shrink-0 flex-col border-r border-gray-200">
        {/* Logo: text only, no decorative block */}
        <div className="px-6 py-5">
          <span className="text-sm font-bold tracking-tight text-black">Maestro</span>
        </div>
        <nav className="flex-1 px-3" aria-label="Main">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setTab(item.id)}
              className={cn('flex items-center gap-3 w-full px-3 py-2 text-sm border-l-2 transition-none',
                tab === item.id
                  ? 'border-black text-black font-semibold'
                  : 'border-transparent text-gray-400 hover:text-black hover:border-gray-300')}>
              {item.icon} {item.label}
            </button>
          ))}
        </nav>
        <div className="px-3 py-3 border-t border-gray-200">
          <button onClick={handleLogout} className="flex items-center gap-3 w-full px-3 py-2 text-sm text-gray-400 hover:text-black border-l-2 border-transparent hover:border-gray-300 transition-none">
            <LogOut className="h-4 w-4" /> Log out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header — no backdrop-blur, no rounded corners */}
        <header className="lg:hidden sticky top-0 z-10 bg-white border-b border-gray-200">
          <div className="flex items-center justify-between px-6 py-3">
            <span className="text-sm font-bold tracking-tight text-black">Maestro</span>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <button key={item.id} onClick={() => setTab(item.id)}
                  className={cn('p-2', tab === item.id ? 'text-black' : 'text-gray-400')}>
                  {item.icon}
                </button>
              ))}
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-2xl w-full mx-auto px-6 lg:px-10 py-8 lg:py-10 pb-24 lg:pb-10">
          {/* Tufte: no motion animations — content appears immediately */}
          {tab === 'today' && <TodayView onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
          {tab === 'today' && <WhisperPostIt onDraft={handleGenerateDraft} />}
          {tab === 'ask' && <AskView />}
          {tab === 'commitments' && <CommitmentsViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
          {tab === 'whisper' && <WhisperViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
          {tab === 'connectors' && <Connectors />}
        </main>
      </div>

      {/* Mobile bottom nav — no backdrop-blur, hairline border */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-gray-200 bg-white" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="grid grid-cols-5">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setTab(item.id)}
              className={cn('flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] min-h-[44px] border-t-2',
                tab === item.id ? 'border-black text-black font-semibold' : 'border-transparent text-gray-400')}>
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

// === TODAY — real API (world-class progressive loading) ===
function TodayView({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [loading, setLoading] = useState(true)
  const [theOne, setTheOne] = useState<any>(null)
  const [changes, setChanges] = useState<any[]>([])
  const [commitments, setCommitments] = useState<any[]>([])
  const [error, setError] = useState('')
  // LATENCY FIX v2 (2026-07-31): the prior code showed a "Still loading" banner
  // whenever the-moment hadn't returned yet — which took 2-9s on cold cache.
  // This made the page feel broken even though commitments + changes had already
  // loaded in <1s. Now we track momentLoading separately and only show the
  // banner after 10s (genuinely broken, not just slow cold cache).
  const [momentLoading, setMomentLoading] = useState(true)
  const [showSlowBanner, setShowSlowBanner] = useState(false)

  useEffect(() => {
    let alive = true

    // LATENCY FIX (v21): progressive loading — fast endpoints first,
    // slow endpoints (the-moment) load in parallel and update in-place.
    // The prior Promise.all blocked ALL rendering until the-moment (9s cold) completed.

    // Phase 1: fast endpoints (< 1s) — render immediately
    ;(async () => {
      try {
        const [shifts, commits] = await Promise.all([
          maestroApi.getTheShifts(),
          maestroApi.getCommitments(),
        ])
        if (!alive) return
        if (shifts.live && shifts.data) setChanges(shifts.data.the_shifts || shifts.data.secondary || [])
        if (commits.live && Array.isArray(commits.data)) setCommitments(commits.data)
        setLoading(false)
      } catch (e) {
        if (alive) { setLoading(false) }
      }
    })()

    // Phase 2: the-moment loads separately (may take 2-9s cold, 0.3s warm)
    setMomentLoading(true)
    ;(async () => {
      try {
        const moment = await maestroApi.getTheMoment()
        if (!alive) return
        if (moment.live && moment.data) setTheOne(moment.data)
        setMomentLoading(false)
      } catch (e) {
        if (alive) { setMomentLoading(false) }
      }
    })()

    // LATENCY FIX v2: only show the "slow" banner after 10s — by then
    // the-moment should have loaded (cold cache is 2-3s). If it hasn't,
    // something is genuinely wrong and the banner is appropriate.
    const slowTimer = setTimeout(() => {
      if (alive && momentLoading) setShowSlowBanner(true)
    }, 10000)

    return () => { alive = false; clearTimeout(slowTimer) }
  }, [])

  if (loading) return <div className="py-16 text-sm text-gray-400">Loading…</div>
  if (error) return (
    <div className="space-y-2">
      {/* Tufte: no colored background, just text + hairline */}
      <p className="text-sm font-semibold text-black">Backend not connected</p>
      <p className="text-xs text-gray-500">{error}</p>
      <p className="text-xs text-gray-400 pt-4">Retry in a moment.</p>
    </div>
  )

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-12">
      {/* Header — strong typographic hierarchy, no decoration */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-black">{greeting}.</h1>
        <p className="text-gray-500 mt-1 text-sm">
          {theOne
            ? 'One promise needs attention.'
            : momentLoading
              ? 'Loading your top priority…'
              : "You're clear today."}
        </p>
      </div>

      {/* Slow banner — Tufte: text + hairline, no colored background */}
      {showSlowBanner && !theOne && (
        <div className="border-l-2 border-gray-400 pl-3 py-1">
          <p className="text-xs font-semibold text-black">Taking longer than usual</p>
          <p className="text-xs text-gray-500 mt-0.5">
            Backend is slow. Your commitments are loaded — top priority will appear when ready.
          </p>
        </div>
      )}

      {/* Loading placeholder — Tufte: text only, no skeleton animation */}
      {momentLoading && !theOne && (
        <p className="text-sm text-gray-300 italic">Loading top priority…</p>
      )}

      {/* The Moment — clean text block, no card chrome */}
      {theOne && theOne.commitment && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Top Priority</p>
          <div className="border-l-2 border-black pl-4">
            <p className="text-sm font-semibold text-black">
              {theOne.commitment.text || theOne.commitment.action || ''}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {theOne.commitment.entity || 'Unknown'}
              {theOne.commitment.deadline ? ` · due ${theOne.commitment.deadline.split('T')[0]}` : ''}
            </p>
            <button
              onClick={() => onDraft(theOne.commitment.entity)}
              disabled={draftBusy}
              className="mt-3 text-xs font-medium text-black underline underline-offset-4 hover:text-gray-600 disabled:opacity-40"
            >
              {draftBusy ? 'Generating…' : 'Draft follow-up'}
            </button>
          </div>
        </div>
      )}

      {/* What Changed — small multiples, aligned rows, no cards */}
      {changes.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">What Changed</p>
            <span className="text-xs text-gray-400">{changes.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
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
                  {/* Tufte: row with positional marker, no background, no rounded */}
                  <div className="flex items-start gap-3 py-3 hover:bg-gray-50">
                    {/* Bertin: shape encodes type (circle = new, square = meaningful) */}
                    <div className={cn('flex-shrink-0 mt-1.5',
                      c.type === 'new' ? 'h-2 w-2 rounded-full bg-black' : c.is_meaningful ? 'h-2 w-2 bg-gray-400' : 'h-2 w-2 border border-gray-300')} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-black leading-snug">{c.text || c.action || ''}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{c.entity || ''}</p>
                    </div>
                  </div>
                </ClickableCard>
              );
            })}
          </div>
        </div>
      )}

      {/* Active Commitments — dense list, small multiples, no card chrome */}
      {commitments.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">Active Commitments</p>
            <span className="text-xs text-gray-400">{commitments.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
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
                <div className="flex items-start gap-3 py-3 hover:bg-gray-50">
                  {/* Bertin: value (darkness) encodes priority, shape is consistent */}
                  <div className={cn('flex-shrink-0 mt-1.5 h-2 w-2',
                    c.is_at_risk ? 'bg-black' : c.deadline ? 'bg-gray-500' : 'border border-gray-300')} />
                  <div className="flex-1 min-w-0">
                    <p className={cn('text-sm leading-snug', c.is_at_risk ? 'font-semibold text-black' : 'text-black')}>{c.text || c.action || ''}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <p className="text-xs text-gray-500">{c.entity || ''}</p>
                      {c.deadline && (
                        <p className="text-xs text-gray-500">{new Date(c.deadline).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</p>
                      )}
                      {c.is_at_risk && (
                        <span className="text-[10px] font-bold text-black uppercase tracking-wide">at risk</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); onDraft(c.entity) }}
                    disabled={draftBusy}
                    className="flex-shrink-0 text-xs text-gray-400 hover:text-black disabled:opacity-40 underline underline-offset-4"
                    title="Draft follow-up"
                  >
                    draft
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
        {/* Tufte: input with hairline border, no rounded corners */}
        <form onSubmit={(e) => { e.preventDefault(); handleAsk(query) }}>
          <div className="flex items-center gap-2 border-b border-gray-300 pb-2">
            <Search className="h-4 w-4 text-gray-400 shrink-0" />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your commitments…"
              className="flex-1 bg-transparent text-black placeholder:text-gray-400 focus:outline-none text-sm" />
          </div>
        </form>

        {/* Tufte: suggestion links, no button chrome */}
        {!answer && !loading && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-4">
            {suggestions.map((s) => (
              <button key={s} onClick={() => { setQuery(s); handleAsk(s) }}
                className="text-xs text-gray-500 hover:text-black underline underline-offset-4">{s}</button>
            ))}
          </div>
        )}

        {/* Tufte: text loading, no spinner */}
        {loading && <p className="mt-8 text-sm text-gray-400">Searching your commitments…</p>}

        {/* Tufte: no motion animation, content appears immediately */}
        {answer && !loading && (
          <div className="mt-8">
            {/* Bertin: value (font weight) encodes confidence, NOT color */}
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-gray-400 tabular-nums">{Math.round((answer.confidence || 0) * 100)}% confidence</span>
              </div>
              <p className={cn('text-base leading-relaxed',
                (answer.confidence || 0) >= 0.7 ? 'font-semibold text-black' : 'text-gray-600')}>
                {answer.answer || 'No answer available.'}
              </p>
            </div>

            {/* Evidence — Tufte: hairline border, no background, no rounded */}
            {answer.evidence_refs && answer.evidence_refs.length > 0 && (
              <div className="mt-6">
                <button onClick={() => setShowEvidence(!showEvidence)}
                  className="text-xs font-medium text-gray-500 hover:text-black mb-2 underline underline-offset-4">
                  Evidence ({answer.evidence_refs.length})
                </button>
                {showEvidence && (
                  <div className="space-y-4">
                    {answer.evidence_refs.map((ev: any, i: number) => (
                      <div key={i} className="border-l-2 border-gray-300 pl-3">
                        <span className="text-[10px] font-medium uppercase tracking-wide text-gray-400">{ev.source_type || ev.source || 'signal'}</span>
                        <p className="text-xs italic text-gray-600 leading-relaxed mt-1">&ldquo;{ev.text || ev.evidence_quote || ''}&rdquo;</p>
                        {ev.signal_id && (
                          <CorrectionButton
                            signalId={ev.signal_id}
                            apiBase={API_BASE}
                            token={getToken() || ''}
                            onCorrected={() => { handleAsk(query) }}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {answer.intelligence_source && (
              <p className="text-xs text-gray-400 mt-4">Source: {answer.intelligence_source}</p>
            )}
          </div>
        )}
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

  if (loading) return <div className="py-16 text-sm text-gray-400">Loading…</div>
  if (error) return <div className="py-8 text-sm text-gray-500">{error}</div>
  if (!commitments.length) return (
    <div className="py-16">
      <p className="text-sm font-semibold text-black">No active commitments.</p>
      <p className="text-xs text-gray-500 mt-1">Connect a tool or create a signal to start tracking.</p>
    </div>
  )

  const sorted = [...commitments].sort((a, b) => (b.is_at_risk ? 1 : 0) - (a.is_at_risk ? 1 : 0))
  const theOne = sorted[0]
  const rest = sorted.slice(1)

  return (
    <div className="space-y-12">
      {/* The One — Tufte: clean text block, no card chrome */}
      {theOne && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-3">Top Priority</p>
          <div className="border-l-2 border-black pl-4">
            <p className="text-sm font-bold text-black">{theOne.text || theOne.action || ''}</p>
            <p className="text-xs text-gray-500 mt-1">
              {theOne.entity || ''}
              {theOne.deadline ? ` · due ${new Date(theOne.deadline).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}` : ''}
              {theOne.is_at_risk ? ' · at risk' : ''}
            </p>
          </div>
        </div>
      )}

      {/* All Active — Tufte: dense list, hairline separators, no card chrome */}
      {rest.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">All Active</p>
            <span className="text-xs text-gray-400">{rest.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
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
                {/* Tufte: row with value-based marker, no card chrome */}
                <div className="flex items-start gap-3 py-3 hover:bg-gray-50">
                  {/* Bertin: value (darkness) encodes confidence, NOT color */}
                  <div className={cn('flex-shrink-0 mt-1.5 h-2 w-2',
                    c.is_at_risk ? 'bg-black' : (c.confidence || 0.5) >= 0.7 ? 'bg-gray-700' : 'border border-gray-400')} />
                  <div className="flex-1 min-w-0">
                    <p className={cn('text-sm leading-snug', c.is_at_risk ? 'font-semibold text-black' : 'text-black')}>{c.text || c.action}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{c.entity}</p>
                  </div>
                  {c.is_at_risk && <span className="text-[10px] font-bold text-black uppercase tracking-wide">at risk</span>}
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

  if (loading) return (
    <div className="space-y-12">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-black">Whispers.</h1>
        <p className="text-gray-500 mt-1 text-sm">Loading your insights…</p>
      </div>
      <p className="text-sm text-gray-300 italic">Loading…</p>
    </div>
  )
  if (error) return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-black">Failed to load</p>
      <p className="text-xs text-gray-500">{error}</p>
    </div>
  )

  // Group whispers by priority
  const highPriority = whispers.filter(w => w.priority === 'high')
  const mediumPriority = whispers.filter(w => w.priority === 'medium' || !w.priority)
  const lowPriority = whispers.filter(w => w.priority === 'low')

  return (
    <div className="space-y-12">
      {/* Header — Tufte: strong typographic hierarchy */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-black">Whispers.</h1>
        <p className="text-gray-500 mt-1 text-sm">
          {whispers.length > 0
            ? `${whispers.length} ${whispers.length === 1 ? 'insight needs' : 'insights need'} attention.`
            : whisperLive
              ? "You're all caught up."
              : 'Loading…'}
        </p>
      </div>

      {/* Loading — Tufte: text only, no colored banner */}
      {!whisperLive && !whispers.length && (
        <p className="text-sm text-gray-300 italic">Loading whispers…</p>
      )}

      {/* Empty state — Tufte: text only, no decorative circle/icon */}
      {whisperLive && whispers.length === 0 && (
        <div className="py-12">
          <p className="text-sm font-semibold text-black">All caught up.</p>
          <p className="text-xs text-gray-500 mt-1">No proactive insights. Maestro is monitoring your commitments.</p>
        </div>
      )}

      {/* High priority — Tufte: dense list with hairlines, value encodes priority */}
      {highPriority.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-black">Needs Attention</p>
            <span className="text-xs text-gray-400">{highPriority.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
            {highPriority.map((w, i) => (
              <WhisperRow
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

      {/* Medium priority */}
      {mediumPriority.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Worth Knowing</p>
            <span className="text-xs text-gray-400">{mediumPriority.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
            {mediumPriority.map((w, i) => (
              <WhisperRow
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

      {/* Low priority */}
      {lowPriority.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">FYI</p>
            <span className="text-xs text-gray-400">{lowPriority.length}</span>
          </div>
          <div className="divide-y divide-gray-100">
            {lowPriority.map((w, i) => (
              <WhisperRow
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

// Tufte/Bertin whisper row — no card chrome, value encodes priority, shape encodes type
function WhisperRow({
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

  // Bertin: value (font weight/darkness) encodes priority, NOT color
  const titleClass = priority === 'high'
    ? 'text-sm font-bold text-black'
    : priority === 'medium'
      ? 'text-sm font-semibold text-black'
      : 'text-sm font-normal text-gray-700'

  // Bertin: shape encodes type (circle = critical, square = deadline, triangle = stale)
  const shapeClass = wType === 'critical_signal'
    ? 'h-2 w-2 rounded-full bg-black'
    : wType === 'deadline_approaching'
      ? 'h-2 w-2 bg-black'
      : wType === 'stale_commitment'
        ? 'h-0 w-0 border-l-[4px] border-r-[4px] border-b-[6px] border-l-transparent border-r-transparent border-b-black'
        : 'h-2 w-2 border border-gray-400'

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
      <div className="flex items-start gap-3 py-3 hover:bg-gray-50">
        {/* Bertin: shape marker — consistent position, varies by type */}
        <div className="flex-shrink-0 mt-1.5 flex items-center justify-center w-3">
          <div className={shapeClass} />
        </div>
        <div className="flex-1 min-w-0">
          {/* Tufte: label close to data, no distant legend */}
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[10px] font-medium uppercase tracking-wide text-gray-400">{wType.replace(/_/g, ' ')}</span>
          </div>
          <p className={titleClass}>{title}</p>
          {body && (
            <p className={cn('text-xs text-gray-500 mt-1', !expanded && 'line-clamp-2')}>
              {body}
            </p>
          )}
          {body && body.length > 120 && (
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
              className="text-xs text-gray-400 hover:text-black mt-1 underline underline-offset-4"
            >
              {expanded ? 'less' : 'more'}
            </button>
          )}
        </div>
      </div>
      {/* Action — Tufte: text link, no button chrome */}
      {entity && entity !== 'Insight' && (
        <div className="pl-6 pb-3">
          <button
            onClick={(e) => { e.stopPropagation(); onDraft(entity) }}
            disabled={draftBusy}
            className="text-xs text-gray-400 hover:text-black disabled:opacity-40 underline underline-offset-4"
          >
            {draftBusy ? 'Generating…' : 'Draft follow-up'}
          </button>
        </div>
      )}
    </ClickableCard>
  )
}

