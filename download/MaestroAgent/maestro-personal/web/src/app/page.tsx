'use client'

import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Sun, Search, Calendar, Zap, MoreHorizontal, Mail, MessageSquare, RefreshCw, CheckCircle2, Plus, X, Send, FileText, Loader2, Unplug } from 'lucide-react'
import type { ViewTab, Commitment } from '@/lib/types'
import { calculateImportance, getLayoutMode, formatTimeUntil, getConfidenceStyle } from '@/lib/importance'
import { mockCommitments, mockWhispers, mockChanges } from '@/lib/mockData'
import { TheOne } from '@/components/maestro/TheOne'
import { AskView } from '@/components/maestro/AskView'
import { WhisperView } from '@/components/maestro/WhisperView'
import { CommitmentsView } from '@/components/maestro/CommitmentsView'
import { maestroApi } from '@/lib/maestro-api'

export default function Home() {
  const [tab, setTab] = useState<ViewTab>('today')

  const sortedCommitments = [...mockCommitments].sort(
    (a, b) => calculateImportance(b) - calculateImportance(a),
  )
  const theOne = sortedCommitments[0]
  const rest = sortedCommitments.slice(1)

  const navItems: { id: ViewTab; label: string; icon: React.ReactNode }[] = [
    { id: 'today', label: 'Today', icon: <Sun className="h-4 w-4" /> },
    { id: 'ask', label: 'Ask', icon: <Search className="h-4 w-4" /> },
    { id: 'commitments', label: 'Commitments', icon: <Calendar className="h-4 w-4" /> },
    { id: 'whisper', label: 'Whisper', icon: <Zap className="h-4 w-4" /> },
    { id: 'more', label: 'Connectors', icon: <Unplug className="h-4 w-4" /> },
  ]

  return (
    <div className="min-h-screen flex bg-white">
      {/* Desktop sidebar — left side, like the old AppShell */}
      <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-gray-100 bg-white">
        <div className="p-5 flex items-center gap-3">
          <div className="h-7 w-7 rounded-md bg-gray-900 flex items-center justify-center">
            <span className="text-white text-xs font-bold">M</span>
          </div>
          <span className="font-semibold text-sm tracking-tight text-gray-900">Maestro</span>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-1" aria-label="Main">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                'flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm transition-colors',
                tab === item.id
                  ? 'bg-gray-100 text-gray-900 font-medium'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-50',
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="p-3 border-t border-gray-100">
          <p className="text-xs text-gray-300 px-3">Personal Intelligence</p>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header — only on small screens */}
        <header className="lg:hidden sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-gray-100">
          <div className="flex items-center justify-between px-6 py-3">
            <span className="font-semibold text-sm tracking-tight text-gray-900">Maestro</span>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setTab(item.id)}
                  className={cn(
                    'p-1.5 rounded-lg transition-colors',
                    tab === item.id ? 'bg-gray-100 text-gray-900' : 'text-gray-400',
                  )}
                >
                  {item.icon}
                </button>
              ))}
            </nav>
          </div>
        </header>

        <main className="flex-1 max-w-2xl w-full mx-auto px-6 lg:px-10 py-8 lg:py-10 pb-24 lg:pb-10">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -2 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            >
              {tab === 'today' && <TodayView theOne={theOne} rest={rest} />}
              {tab === 'ask' && <AskView />}
              {tab === 'commitments' && <CommitmentsView commitments={mockCommitments} />}
              {tab === 'whisper' && <WhisperView whispers={mockWhispers} />}
              {tab === 'more' && <ConnectorsView />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-gray-100 bg-white/95 backdrop-blur-sm" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="grid grid-cols-5">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                'flex flex-col items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-colors min-h-[44px]',
                tab === item.id ? 'text-gray-900' : 'text-gray-400',
              )}
            >
              {item.icon}
              <span className="truncate max-w-full px-1">{item.label}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  )
}

// === TODAY VIEW ===
function TodayView({ theOne, rest }: { theOne: Commitment; rest: Commitment[] }) {
  const score = calculateImportance(theOne)
  const mode = getLayoutMode(score)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">{greeting}.</h1>
        {mode === 'dominant' || mode === 'prominent' ? (
          <p className="text-gray-400 mt-2 text-base">You have {mode === 'dominant' ? 'one promise' : 'a few promises'} that need attention.</p>
        ) : (
          <p className="text-gray-400 mt-2 text-base">Here&rsquo;s what needs your attention.</p>
        )}
      </div>
      <TheOne commitment={theOne} />
      <div className={cn(mode === 'dominant' && 'opacity-60')}>
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">What Changed</p>
        <div className="space-y-3">
          {mockChanges.map((change, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="flex items-start gap-3">
              <div className={cn('flex-shrink-0 mt-1 h-1.5 w-1.5 rounded-full', change.type === 'new' && 'bg-blue-400', change.type === 'transition' && 'bg-amber-400', change.type === 'deadline' && 'bg-red-400', change.type === 'completion' && 'bg-green-400')} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 leading-relaxed">{change.text}</p>
                <p className="text-xs text-gray-400 mt-0.5 tabular-nums">{change.entity} · {change.timeAgo}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}

// === CONNECTORS VIEW — wired to real API ===
function ConnectorsView() {
  const [connectors, setConnectors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<any[]>([])
  const [generatingDraft, setGeneratingDraft] = useState(false)
  const [error, setError] = useState('')

  const loadConnectors = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data, live } = await maestroApi.listConnectors()
      if (live && data?.connectors) {
        setConnectors(data.connectors)
      } else {
        setError('Backend not connected. Showing demo connectors.')
        setConnectors([])
      }
    } catch (e) {
      setError('Failed to load connectors.')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDrafts = useCallback(async () => {
    try {
      const { data, live } = await maestroApi.listDrafts('pending')
      if (live && data?.drafts) {
        setDrafts(data.drafts)
      }
    } catch (e) {
      // Drafts are optional — don't show error
    }
  }, [])

  useEffect(() => {
    loadConnectors()
    loadDrafts()
  }, [loadConnectors, loadDrafts])

  const handleSync = async (provider: string) => {
    setSyncing(provider)
    try {
      const { data, live } = await maestroApi.ingestConnector(provider)
      if (live) {
        alert(`Synced ${data.ingested} emails. ${data.new_commitments} new commitments, ${data.duplicates} duplicates.`)
        loadConnectors()
      } else {
        alert('Backend not connected.')
      }
    } catch (e) {
      alert('Sync failed. Check your connection.')
    } finally {
      setSyncing(null)
    }
  }

  const handleGenerateDraft = async () => {
    setGeneratingDraft(true)
    try {
      const { data, live } = await maestroApi.generateAutoDraft('gmail', 'follow_up')
      if (live && data) {
        alert(`Draft generated!\n\nSubject: ${data.subject || '(no subject)'}\n\n${data.body?.slice(0, 200) || ''}...`)
        loadDrafts()
      } else {
        alert('Backend not connected. Cannot generate draft.')
      }
    } catch (e) {
      alert('Draft generation failed. Make sure Gmail is connected.')
    } finally {
      setGeneratingDraft(false)
    }
  }

  const handleResolveDraft = async (draftId: string, resolution: string) => {
    try {
      await maestroApi.resolveDraft(draftId, resolution)
      loadDrafts()
    } catch (e) {
      alert('Failed to resolve draft.')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-10">
      {error && (
        <div className="text-sm text-amber-600 bg-amber-50 rounded-lg p-3">{error}</div>
      )}

      {/* Connectors */}
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">Connectors</p>
        <div className="space-y-3">
          {connectors.length === 0 && !error && (
            <p className="text-sm text-gray-400">No connectors loaded.</p>
          )}
          {connectors.map((c, i) => (
            <ConnectorCard key={c.provider || i} connector={c} onSync={() => handleSync(c.provider)} syncing={syncing === c.provider} />
          ))}
        </div>
      </div>

      {/* Draft Emails */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400">Draft Emails</p>
          <button
            onClick={handleGenerateDraft}
            disabled={generatingDraft}
            className="flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:border-gray-300 transition-colors disabled:opacity-50"
          >
            {generatingDraft ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
            Generate Follow-up
          </button>
        </div>
        <div className="space-y-3">
          {drafts.length === 0 && (
            <p className="text-sm text-gray-400">No pending drafts. Click "Generate Follow-up" to create one.</p>
          )}
          {drafts.map((d, i) => (
            <DraftCard key={d.draft_id || i} draft={d} onResolve={handleResolveDraft} />
          ))}
        </div>
      </div>
    </div>
  )
}

function ConnectorCard({ connector, onSync, syncing }: { connector: any; onSync: () => void; syncing: boolean }) {
  const connected = connector.connected
  const provider = connector.provider || 'unknown'
  const iconMap: Record<string, React.ReactNode> = {
    gmail: <Mail className="h-5 w-5" />,
    calendar: <Calendar className="h-5 w-5" />,
    slack: <MessageSquare className="h-5 w-5" />,
    github: <FileText className="h-5 w-5" />,
  }

  return (
    <div className={cn('flex items-center gap-4 py-4 px-5 rounded-xl transition-colors', connected ? 'bg-white border border-gray-100' : 'bg-gray-50/50')}>
      <div className={cn('flex-shrink-0 flex items-center justify-center h-10 w-10 rounded-lg', connected ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500')}>
        {iconMap[provider] || <Unplug className="h-5 w-5" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-sm text-gray-900">{connector.name || provider}</h3>
          {connected && <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />}
          {connected && <span className="text-xs text-green-600 font-medium">Active</span>}
        </div>
        <p className="text-xs text-gray-400 mt-0.5">{connector.ingest_description || `Connect your ${connector.name || provider} account`}</p>
        {connected && connector.commitments_ingested > 0 && (
          <p className="text-xs text-gray-400 mt-1 tabular-nums">{connector.commitments_ingested} commitments ingested</p>
        )}
      </div>
      <div className="flex-shrink-0 flex items-center gap-2">
        {connected && (
          <button onClick={onSync} disabled={syncing} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
            {syncing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            Sync
          </button>
        )}
        {connected ? (
          <button className="text-xs text-gray-400 hover:text-red-500 px-2 py-1.5">Disconnect</button>
        ) : (
          <button className="flex items-center gap-1 text-xs font-medium text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded-lg bg-white border border-gray-200 hover:border-gray-300">
            <Plus className="h-3 w-3" /> Connect
          </button>
        )}
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
          <div className="flex items-center gap-2 mb-1">
            {draft.llm_generated && <span className="text-xs text-blue-500 font-medium">AI-generated</span>}
            {draft.derived && <span className="text-xs text-gray-400">Derived</span>}
          </div>
          <h4 className="font-medium text-sm text-gray-900 truncate">{draft.subject || '(no subject)'}</h4>
          <p className="text-xs text-gray-400 mt-0.5">To: {draft.to_email || 'Unknown'} · {draft.provider || 'gmail'}</p>
        </div>
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-gray-400 hover:text-gray-600">
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>
      {expanded && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="overflow-hidden mt-3">
          <div className="pl-3 border-l-2 border-gray-100">
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{draft.body || '(empty body)'}</p>
          </div>
        </motion.div>
      )}
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-50">
        <button onClick={() => onResolve(draft.draft_id, 'approved')} className="flex items-center gap-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 px-3 py-1.5 rounded-lg transition-colors">
          <Send className="h-3 w-3" /> Approve & Send
        </button>
        <button onClick={() => onResolve(draft.draft_id, 'denied')} className="text-xs text-gray-400 hover:text-red-500 px-3 py-1.5">Deny</button>
        <button onClick={() => onResolve(draft.draft_id, 'use_draft')} className="text-xs text-gray-400 hover:text-gray-600 px-3 py-1.5">Use as draft</button>
      </div>
    </div>
  )
}
