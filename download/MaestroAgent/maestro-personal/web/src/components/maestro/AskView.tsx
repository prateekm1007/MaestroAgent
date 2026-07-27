'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Search, ChevronDown, FileText, Clock, Sparkles, Loader2 } from 'lucide-react'
import { maestroApi } from '@/lib/maestro-api'

export function AskView() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [showEvidence, setShowEvidence] = useState(false)
  const [showReasoning, setShowReasoning] = useState(false)
  const [error, setError] = useState('')

  const handleAsk = async (q: string) => {
    if (!q.trim()) return
    setLoading(true)
    setAnswer(null)
    setError('')
    try {
      const { data, live } = await maestroApi.ask(q)
      if (live && data) {
        setAnswer(data)
      } else {
        setError('Backend not connected. Please try again.')
      }
    } catch (e) {
      setError('Request failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const suggestions = [
    'What did I promise Maria?',
    "What's at risk today?",
    'What did I commit to this week?',
  ]

  const confidence = answer?.confidence ?? 0
  const confColor = confidence >= 0.7 ? '#059669' : confidence >= 0.4 ? '#D97706' : '#6B7280'
  const confLabel = confidence >= 0.7 ? 'High confidence' : confidence >= 0.4 ? 'Moderate confidence' : 'Low confidence'
  const confPrefix = confidence >= 0.7 ? 'Yes.' : confidence >= 0.4 ? 'Probably.' : "I'm not fully confident, but"

  return (
    <div className="flex flex-col items-center w-full">
      <div className="w-full max-w-2xl">
        <form onSubmit={(e) => { e.preventDefault(); handleAsk(query) }} className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about your commitments..."
            className="w-full pl-11 pr-4 py-3.5 bg-white rounded-xl border border-gray-200 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400 transition-colors text-sm"
          />
        </form>

        {!answer && !loading && !error && (
          <div className="flex flex-wrap gap-2 mt-4">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); handleAsk(s) }}
                className="px-3 py-1.5 text-sm text-gray-500 bg-gray-50 hover:bg-gray-100 rounded-full transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <div className="mt-8 flex items-center gap-2 text-gray-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Searching your commitment ledger...</span>
          </div>
        )}

        {error && (
          <div className="mt-8 text-sm text-red-500">{error}</div>
        )}

        <AnimatePresence>
          {answer && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="mt-8"
            >
              {/* Direct answer */}
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ background: confColor }} />
                  <span className="text-xs text-gray-400 tabular-nums">
                    {Math.round(confidence * 100)}% · {confLabel}
                  </span>
                </div>
                <p
                  className="text-lg leading-relaxed tracking-tight"
                  style={{ color: confidence >= 0.4 ? '#1A1A1A' : '#6B7280' }}
                >
                  <span className="font-semibold">{confPrefix}</span>{' '}
                  {answer.answer || 'No answer available.'}
                </p>
              </div>

              {/* Evidence */}
              {answer.evidence_refs && answer.evidence_refs.length > 0 && (
                <DisclosureSection
                  label={`Evidence (${answer.evidence_refs.length})`}
                  expanded={showEvidence}
                  onToggle={() => setShowEvidence(!showEvidence)}
                >
                  <div className="space-y-4">
                    {answer.evidence_refs.map((ev: any, i: number) => (
                      <div key={i} className="pl-4 border-l-2 rounded-r-lg" style={{ borderColor: '#2563EB', background: '#F9FAFB' }}>
                        <div className="p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <SourceIcon type={ev.source_type || ev.source || 'signal'} />
                            <span className="text-xs text-gray-500 capitalize">{ev.source_type || ev.source || 'signal'}</span>
                            {ev.timestamp && (
                              <>
                                <span className="text-gray-300">·</span>
                                <span className="text-xs text-gray-400">
                                  {new Date(ev.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </span>
                              </>
                            )}
                          </div>
                          <p className="text-sm italic text-gray-700 leading-relaxed">"{ev.text || ev.evidence_quote || ''}"</p>
                          {ev.entity && <p className="text-xs text-gray-400 mt-2">{ev.entity}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </DisclosureSection>
              )}

              {/* Confidence & Reasoning */}
              {answer.calibration_note && (
                <DisclosureSection
                  label="Confidence & Reasoning"
                  expanded={showReasoning}
                  onToggle={() => setShowReasoning(!showReasoning)}
                >
                  <div>
                    <div className="flex items-center gap-3 mb-4">
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${confidence * 100}%` }}
                          transition={{ duration: 0.6, ease: 'easeOut' }}
                          className="h-full rounded-full"
                          style={{ background: confColor }}
                        />
                      </div>
                      <span className="text-sm font-medium text-gray-600 tabular-nums">{Math.round(confidence * 100)}%</span>
                    </div>
                    <p className="text-sm text-gray-500 leading-relaxed">{answer.calibration_note}</p>
                  </div>
                </DisclosureSection>
              )}

              {/* Intelligence source */}
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

function DisclosureSection({
  label,
  expanded,
  onToggle,
  children,
}: {
  label: string
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  return (
    <div className="mt-4">
      <button
        onClick={onToggle}
        className="flex items-center gap-1 text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors mb-2"
      >
        {label}
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SourceIcon({ type }: { type: string }) {
  const icons: Record<string, React.ReactNode> = {
    email: <FileText className="h-3.5 w-3.5 text-gray-400" />,
    slack: <Sparkles className="h-3.5 w-3.5 text-gray-400" />,
    calendar: <Clock className="h-3.5 w-3.5 text-gray-400" />,
    manual: <FileText className="h-3.5 w-3.5 text-gray-400" />,
  }
  return icons[type] || icons.manual
}
