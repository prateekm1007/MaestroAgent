'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ChevronDown, Search, Sparkles, FileText, Clock } from 'lucide-react'
import type { AskAnswer } from '@/lib/types'
import { getConfidenceStyle, getConfidencePrefix } from '@/lib/importance'
import { mockAskAnswer, mockAskAnswerLow, mockAskAnswerEmpty } from '@/lib/mockData'

export function AskView() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<AskAnswer | null>(null)
  const [loading, setLoading] = useState(false)

  const handleAsk = (q: string) => {
    if (!q.trim()) return
    setLoading(true)
    setAnswer(null)
    // Simulate API call with mock data
    setTimeout(() => {
      if (q.toLowerCase().includes('maria')) {
        setAnswer(mockAskAnswer)
      } else if (q.toLowerCase().includes('security')) {
        setAnswer(mockAskAnswerLow)
      } else {
        setAnswer({ ...mockAskAnswerEmpty, query: q })
      }
      setLoading(false)
    }, 800)
  }

  const suggestions = [
    'What did I promise Maria?',
    'What\u2019s at risk today?',
    'Did I promise to review the security audit?',
  ]

  return (
    <div className="flex flex-col items-center w-full">
      {/* Search — floating, minimal */}
      <div className="w-full max-w-2xl">
        <form
          onSubmit={(e) => { e.preventDefault(); handleAsk(query) }}
          className="relative"
        >
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about your commitments..."
            className="w-full pl-11 pr-4 py-3.5 bg-white rounded-xl border border-gray-200 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400 transition-colors text-sm"
            style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}
          />
        </form>

        {/* Suggestion chips */}
        {!answer && !loading && (
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

        {/* Loading state */}
        {loading && (
          <div className="mt-8 flex items-center gap-2 text-gray-400">
            <div className="h-2 w-2 bg-gray-300 rounded-full animate-pulse" />
            <span className="text-sm">Searching your commitment ledger...</span>
          </div>
        )}

        {/* Answer */}
        <AnimatePresence>
          {answer && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="mt-8"
            >
              <AnswerCard answer={answer} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function AnswerCard({ answer }: { answer: AskAnswer }) {
  const [showEvidence, setShowEvidence] = useState(false)
  const [showReasoning, setShowReasoning] = useState(false)
  const [showRelated, setShowRelated] = useState(false)

  // Empty state
  if (answer.confidence === 0 || !answer.answer) {
    return (
      <div className="text-center py-12">
        <p className="text-lg text-gray-500 mb-2">I don&rsquo;t have evidence for that.</p>
        <p className="text-sm text-gray-400 max-w-md mx-auto">
          I checked your signals and commitments but found nothing matching
          &ldquo;{answer.query}&rdquo;.
        </p>
        <p className="text-sm text-gray-400 mt-4">
          If you&rsquo;d like,{' '}
          <button className="text-blue-600 underline underline-offset-2 hover:text-blue-700">
            connect your Gmail
          </button>{' '}
          to give me more context.
        </p>
      </div>
    )
  }

  const confStyle = getConfidenceStyle(answer.confidence)
  const prefix = getConfidencePrefix(answer.confidence)

  return (
    <div>
      {/* Level 1: Direct Answer — conversational */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <div
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: confStyle.color }}
          />
          <span className="text-xs text-gray-400 tabular-nums">
            {Math.round(answer.confidence * 100)}% · {confStyle.label}
          </span>
        </div>
        <p
          className="text-lg leading-relaxed tracking-tight"
          style={{ color: answer.confidence >= 0.7 ? '#1A1A1A' : '#6B7280' }}
        >
          <span className="font-semibold">{prefix}</span>{' '}
          {answer.answer.replace(/^(Yes\.|Probably\.|I'm not fully confident, but)\s*/i, '')}
        </p>
      </div>

      {/* Level 2: Evidence — Tufte legal exhibit style */}
      {answer.evidence.length > 0 && (
        <DisclosureSection
          label="Evidence"
          expanded={showEvidence}
          onToggle={() => setShowEvidence(!showEvidence)}
        >
          <div className="space-y-4">
            {answer.evidence.map((ev, i) => (
              <div
                key={i}
                className="pl-4 border-l-2 rounded-r-lg"
                style={{ borderColor: '#2563EB', background: '#F9FAFB' }}
              >
                <div className="p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <SourceIcon type={ev.source.type} />
                    <span className="text-xs text-gray-500 capitalize">
                      {ev.source.type}
                    </span>
                    <span className="text-gray-300">·</span>
                    <span className="text-xs text-gray-400">
                      {new Date(ev.source.timestamp).toLocaleDateString('en-US', {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                      })}{' '}
                      {new Date(ev.source.timestamp).toLocaleTimeString('en-US', {
                        hour: 'numeric',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <p className="text-sm italic text-gray-700 leading-relaxed">
                    &ldquo;{ev.text}&rdquo;
                  </p>
                  {ev.source.sender && (
                    <p className="text-xs text-gray-400 mt-2">
                      from {ev.source.sender}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </DisclosureSection>
      )}

      {/* Level 3: Confidence & Reasoning */}
      {answer.reasoning.length > 0 && (
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
                  animate={{ width: `${answer.confidence * 100}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut' }}
                  className="h-full rounded-full"
                  style={{ background: confStyle.color }}
                />
              </div>
              <span className="text-sm font-medium text-gray-600 tabular-nums">
                {Math.round(answer.confidence * 100)}%
              </span>
            </div>
            <ul className="space-y-2">
              {answer.reasoning.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-500">
                  <span className="text-gray-300 mt-0.5">·</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        </DisclosureSection>
      )}

      {/* Level 4: Related Commitments */}
      {answer.relatedCommitments.length > 0 && (
        <DisclosureSection
          label="Related"
          expanded={showRelated}
          onToggle={() => setShowRelated(!showRelated)}
        >
          <div className="space-y-2">
            {answer.relatedCommitments.map((rc, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <div>
                  <p className="text-sm text-gray-700">{rc.text}</p>
                  <p className="text-xs text-gray-400">
                    {rc.owner === 'user' ? 'You promised' : `${rc.entity} promised`} ·{' '}
                    {new Date(rc.dueDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </p>
                </div>
                <div
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    new Date(rc.dueDate).getTime() < Date.now() ? 'bg-red-400' : 'bg-gray-300',
                  )}
                />
              </div>
            ))}
          </div>
        </DisclosureSection>
      )}
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
