'use client'

import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Sun, Search, Calendar, Zap, Unplug, Mail, MessageSquare, FileText, RefreshCw, CheckCircle2, Plus, Send, Loader2, LogOut, Sparkles, PenLine } from 'lucide-react'
import { maestroApi, getToken, setToken, clearToken } from '@/lib/maestro-api'
import { Login } from '@/components/maestro/Login'
import { DraftApprovalModal, type DraftWithMeta } from '@/components/maestro/DraftApprovalModal'
import ClickableCard from '@/components/maestro/ClickableCard'
import { calculateImportance, getLayoutMode, getConfidenceStyle } from '@/lib/importance'
import { TheOne } from '@/components/maestro/TheOne'
import { WhisperView } from '@/components/maestro/WhisperView'
import { CommitmentsView } from '@/components/maestro/CommitmentsView'

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
  const handleResolveDraft = async (draft: DraftWithMeta, resolution: 'approve' | 'deny' | 'use_draft') => {
    setDraftResolving(true)
    try {
      await maestroApi.resolveDraft(draft.draft_id, resolution)
      setDraftForReview(null)
    } catch {
      alert('Failed to resolve draft.')
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
              {tab === 'ask' && <AskView />}
              {tab === 'commitments' && <CommitmentsViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
              {tab === 'whisper' && <WhisperViewReal onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
              {tab === 'connectors' && <ConnectorsView onDraft={handleGenerateDraft} draftBusy={draftBusy} />}
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
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [moment, shifts] = await Promise.all([
          maestroApi.getTheMoment(),
          maestroApi.getTheShifts(),
        ])
        if (!alive) return
        if (moment.live && moment.data) setTheOne(moment.data)
        if (shifts.live && shifts.data) setChanges(shifts.data.the_shifts || shifts.data.secondary || [])
        setLoading(false)
      } catch (e) {
        if (alive) { setError('Failed to load. Please try again.'); setLoading(false) }
      }
    })()
    return () => { alive = false }
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>
  if (error) return <div className="text-sm text-red-500 py-8">{error}</div>

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">{greeting}.</h1>
        <p className="text-gray-400 mt-2 text-base">
          {theOne ? 'You have one promise that needs attention.' : 'You\'re clear today. No commitments need attention.'}
        </p>
      </div>

      {theOne && theOne.commitment && (
        <div>
          <ClickableCard
            commitment={{
              commitment_id: theOne.commitment.signal_id || 'the-one',
              entity: theOne.commitment.entity || '',
              text: theOne.commitment.text || theOne.commitment.action || '',
              state: theOne.commitment.is_at_risk ? 'at_risk' : 'active',
              confidence: theOne.commitment.confidence || 0.7,
              deadline_text: theOne.commitment.deadline,
              source_signal_id: theOne.commitment.signal_id
            }}
            apiBase={API_BASE}
            token={getToken() || ''}
          >
            <TheOne commitment={{
              id: theOne.commitment.signal_id || 'the-one',
              entity: theOne.commitment.entity || '',
              text: theOne.commitment.text || theOne.commitment.action || '',
              dueDate: theOne.commitment.deadline || new Date().toISOString(),
              state: theOne.commitment.is_at_risk ? 'at_risk' : 'active',
              confidence: theOne.commitment.confidence || 0.7,
              importance: theOne.commitment.is_at_risk ? 'high' : 'medium',
              isBlocking: false,
              owner: 'user',
              source: { type: 'email', snippet: theOne.commitment.text || '', timestamp: theOne.commitment.created_at || '', sender: '' },
              createdAt: theOne.commitment.created_at || '',
            }} />
          </ClickableCard>
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
            {changes.slice(0, 5).map((c, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className={cn('flex-shrink-0 mt-1 h-1.5 w-1.5 rounded-full',
                  c.type === 'new' ? 'bg-blue-400' : c.is_meaningful ? 'bg-amber-400' : 'bg-gray-300')} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-700 leading-relaxed">{c.text || c.action || JSON.stringify(c)}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{c.entity || ''}</p>
                </div>
              </div>
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
                                <span className="text-xs text-gray-400">{ev.source_type || ev.source || 'signal'}</span>
                                <p className="text-sm italic text-gray-700 leading-relaxed mt-1">"{ev.text || ev.evidence_quote || ''}"</p>
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
          
            <TheOne commitment={{
              id: theOne.signal_id || 'c1', entity: theOne.entity || '', text: theOne.text || theOne.action || '',
              dueDate: theOne.deadline || new Date().toISOString(), state: theOne.is_at_risk ? 'at_risk' : 'active',
              confidence: theOne.confidence || 0.7, importance: theOne.is_at_risk ? 'high' : 'medium', isBlocking: false,
              owner: 'user', source: { type: 'email', snippet: theOne.text || '', timestamp: '', sender: '' }, createdAt: '',
            }} />
          
        </div>
      )}
      {rest.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">All Active ({rest.length})</p>
          <div className="space-y-2">
            {rest.map((c, i) => (
              
                <div className="flex items-center gap-3 py-3 px-4 bg-white rounded-lg border border-gray-100">
                  <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: (c.confidence || 0.5) >= 0.7 ? '#059669' : '#D97706' }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-700 truncate">{c.text || c.action}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{c.entity}</p>
                  </div>
                  {c.is_at_risk && <span className="text-xs text-red-500 font-medium">At risk</span>}
                </div>
              
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// === WHISPER — real API ===
function WhisperViewReal({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [loading, setLoading] = useState(true)
  const [whispers, setWhispers] = useState<any[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const { data, live } = await maestroApi.getWhispers()
        if (!alive) return
        const list = Array.isArray(data) ? data : (data ? [data] : [])
        if (live) setWhispers(list)
        setLoading(false)
      } catch { if (alive) { setError('Failed to load whispers.'); setLoading(false) } }
    })()
    return () => { alive = false }
  }, [])

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>
  if (error) return <div className="text-sm text-red-500 py-8">{error}</div>
  if (!whispers.length) return (
    <div className="text-center py-16">
      <p className="text-lg text-gray-400">All caught up.</p>
      <p className="text-sm text-gray-400 mt-1">No proactive insights right now.</p>
    </div>
  )

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      {whispers.map((w, i) => (
        <div key={i} className={cn('p-5 rounded-2xl',
          w.type === 'at_risk' ? 'bg-red-50/80' : w.type === 'preparation' ? 'bg-blue-50/80' : w.type === 'opportunity' ? 'bg-green-50/80' : 'bg-gray-50')}>
          <h3 className="font-semibold text-sm text-gray-900">{w.title || w.text || w.message || 'Insight'}</h3>
          {(w.context || w.detail) && <p className="text-sm text-gray-500 mt-1">{w.context || w.detail}</p>}
          {w.suggested_actions?.length > 0 && (
            <div className="flex items-center gap-2 mt-3">
              {w.suggested_actions.map((a: any, j: number) => (
                <button key={j} className="text-xs font-medium text-gray-600 px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:border-gray-300">{a.label || a}</button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// === CONNECTORS — real API ===
function ConnectorsView({ onDraft, draftBusy }: { onDraft: (entity: string) => void; draftBusy: boolean }) {
  const [connectors, setConnectors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<any[]>([])
  const [generatingDraft, setGeneratingDraft] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [connRes, draftRes] = await Promise.all([
        maestroApi.listConnectors(),
        maestroApi.listDrafts('pending'),
      ])
      if (connRes.live && connRes.data?.connectors) setConnectors(connRes.data.connectors)
      if (draftRes.live && draftRes.data?.drafts) setDrafts(draftRes.data.drafts)
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSync = async (provider: string) => {
    setSyncing(provider)
    try {
      const { data, live } = await maestroApi.ingestConnector(provider)
      if (live) alert(`Synced ${data.ingested} items. ${data.new_commitments} new commitments.`)
      load()
    } catch { alert('Sync failed.') }
    finally { setSyncing(null) }
  }

  const handleGenerateDraft = async () => {
    setGeneratingDraft(true)
    try {
      const { data, live } = await maestroApi.generateAutoDraft('gmail', 'follow_up')
      if (live && data) {
        setDraftForReview(data)
        load()
      } else alert('Backend not connected.')
    } catch { alert('Draft generation failed. Make sure Gmail is connected.') }
    finally { setGeneratingDraft(false) }
  }

  const handleResolveDraft = async (id: string, resolution: string) => {
    try { await maestroApi.resolveDraft(id, resolution); load() }
    catch { alert('Failed to resolve draft.') }
  }

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-gray-300" /></div>

  return (
    <div className="max-w-2xl mx-auto space-y-10">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">Connectors</p>
        <div className="space-y-3">
          {connectors.length === 0 && <p className="text-sm text-gray-400">No connectors loaded.</p>}
          {connectors.map((c, i) => (
            <div key={c.provider || i} className={cn('flex items-center gap-4 py-4 px-5 rounded-xl', c.connected ? 'bg-white border border-gray-100' : 'bg-gray-50/50')}>
              <div className={cn('flex items-center justify-center h-10 w-10 rounded-lg flex-shrink-0', c.connected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500')}>
                {c.provider === 'gmail' ? <Mail className="h-5 w-5" /> : c.provider === 'calendar' ? <Calendar className="h-5 w-5" /> : c.provider === 'slack' ? <MessageSquare className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-sm text-gray-900">{c.name || c.provider}</h3>
                  {c.connected && <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />}
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{c.ingest_description || `Connect your ${c.name || c.provider}`}</p>
                {c.connected && c.commitments_ingested > 0 && <p className="text-xs text-gray-400 mt-1 tabular-nums">{c.commitments_ingested} commitments ingested</p>}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {c.connected && <button onClick={() => handleSync(c.provider)} disabled={syncing === c.provider} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-50 disabled:opacity-50">{syncing === c.provider ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}Sync</button>}
                {c.connected ? <button className="text-xs text-gray-400 hover:text-red-500 px-2 py-1.5">Disconnect</button> : <button className="flex items-center gap-1 text-xs font-medium text-gray-600 px-3 py-1.5 rounded-lg bg-white border border-gray-200"><Plus className="h-3 w-3" />Connect</button>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400">Draft Emails</p>
          <button onClick={handleGenerateDraft} disabled={generatingDraft} className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:border-gray-300 disabled:opacity-50">
            {generatingDraft ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}Generate Follow-up
          </button>
        </div>
        <div className="space-y-3">
          {drafts.length === 0 && <p className="text-sm text-gray-400">No pending drafts. Click "Generate Follow-up" to create one.</p>}
          {drafts.map((d, i) => (
            <DraftCard key={d.draft_id || i} draft={d} onResolve={handleResolveDraft} />
          ))}
        </div>
      </div>
    </div>
  )
}

function DraftCard({ draft, onResolve }: { draft: any; onResolve: (id: string, resolution: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {draft.llm_generated && <span className="text-xs text-blue-500 font-medium">AI-generated </span>}
          <h4 className="font-medium text-sm text-gray-900 truncate">{draft.subject || '(no subject)'}</h4>
          <p className="text-xs text-gray-400 mt-0.5">To: {draft.to_email || 'Unknown'} · {draft.provider || 'gmail'}</p>
        </div>
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-gray-400 hover:text-gray-600">{expanded ? 'Collapse' : 'Expand'}</button>
      </div>
      {expanded && <div className="mt-3 pl-3 border-l-2 border-gray-100"><p className="text-sm text-gray-600 whitespace-pre-wrap">{draft.body || '(empty)'}</p></div>}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-50">
        <button onClick={() => onResolve(draft.draft_id, 'approved')} className="flex items-center gap-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 px-3 py-1.5 rounded-lg"><Send className="h-3 w-3" />Approve & Send</button>
        <button onClick={() => onResolve(draft.draft_id, 'denied')} className="text-xs text-gray-400 hover:text-red-500 px-3 py-1.5">Deny</button>
        <button onClick={() => onResolve(draft.draft_id, 'use_draft')} className="text-xs text-gray-400 hover:text-gray-600 px-3 py-1.5">Use as draft</button>
      </div>
    </div>
  )
}
