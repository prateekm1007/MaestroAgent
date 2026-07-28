'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ChevronDown, Clock, AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react'
import type { Commitment, LayoutMode } from '@/lib/types'
import { calculateImportance, getLayoutMode, formatTimeUntil, getConfidenceStyle } from '@/lib/importance'
import ClickableCard from './ClickableCard'

interface TheOneProps {
  commitment: Commitment
  apiBase?: string
  token?: string
}

export function TheOne({ commitment, apiBase, token }: TheOneProps) {
  const [expanded, setExpanded] = useState(false)
  const score = calculateImportance(commitment)
  const mode = getLayoutMode(score)
  const confStyle = getConfidenceStyle(commitment.confidence)
  const timeStr = formatTimeUntil(commitment.dueDate)
  const isOverdue = new Date(commitment.dueDate).getTime() < Date.now()

  // Adaptive layout based on importance
  const layoutConfig = getLayoutConfig(mode)

  return (
    <ClickableCard
      commitment={{
        commitment_id: commitment.id,
        entity: commitment.entity,
        text: commitment.text,
        state: commitment.state || 'active',
        confidence: commitment.confidence,
        deadline_text: commitment.dueDate,
        source_signal_id: commitment.id,
      }}
      apiBase={apiBase || 'https://maestroagent-production.up.railway.app'}
      token={token || ''}
    >
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          'relative w-full overflow-hidden rounded-2xl',
          mode === 'dominant' && 'min-h-[55vh] bg-gradient-to-b from-white to-gray-50/50',
          mode === 'prominent' && 'min-h-[38vh] bg-white',
          mode === 'present' && 'min-h-[26vh] bg-white',
          mode === 'quiet' && 'min-h-[18vh] bg-gray-50/50',
        )}
        style={{
          boxShadow: mode === 'dominant'
            ? '0 4px 24px -8px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)'
            : '0 1px 3px rgba(0,0,0,0.04)',
        }}
      >
      {/* Urgency bar — Tufte sparkline-style indicator */}
      <div
        className="absolute top-0 left-0 right-0 h-1"
        style={{
          background: isOverdue ? '#DC2626' : score >= 80 ? '#D97706' : score >= 50 ? '#F59E0B' : '#E5E7EB',
        }}
      />

      <div className={cn('flex flex-col', layoutConfig.padding)}>
        {/* Urgency label */}
        <div className="flex items-center gap-2 mb-3">
          {isOverdue ? (
            <AlertTriangle className="h-4 w-4 text-red-600" />
          ) : score >= 70 ? (
            <Clock className="h-4 w-4 text-amber-600" />
          ) : (
            <Clock className="h-4 w-4 text-gray-400" />
          )}
          <span
            className={cn(
              'font-medium tracking-tight',
              layoutConfig.urgencySize,
              isOverdue ? 'text-red-600' : score >= 70 ? 'text-amber-700' : 'text-gray-500',
            )}
          >
            {timeStr}
          </span>
          {commitment.isBlocking && (
            <span className="ml-auto text-xs font-medium text-gray-400 px-2 py-0.5 rounded-full bg-gray-100">
              Blocking
            </span>
          )}
        </div>

        {/* Entity name — Tufte: direct labeling, minimal decoration */}
        <p className={cn('text-gray-500 font-medium tracking-tight mb-1', layoutConfig.entitySize)}>
          {commitment.entity}
        </p>

        {/* THE commitment — the focal point */}
        <h2
          className={cn(
            'font-semibold tracking-tight text-gray-900 leading-tight',
            layoutConfig.titleSize,
          )}
        >
          {commitment.text}
        </h2>

        {/* Confidence indicator — Bertin: value as visual variable */}
        <div className="flex items-center gap-3 mt-4">
          <div className="flex items-center gap-1.5">
            <div
              className="h-2 w-2 rounded-full"
              style={{ background: confStyle.color }}
            />
            <span className="text-sm text-gray-500 tabular-nums">
              {Math.round(commitment.confidence * 100)}% confidence
            </span>
          </div>
          <span className="text-gray-300">·</span>
          <span className="text-sm text-gray-400">
            from {commitment.source.type}
          </span>
        </div>

        {/* Progressive disclosure: "Why this matters" (merged Briefing) */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="overflow-hidden"
            >
              <div className="mt-5 pt-5 border-t border-gray-100">
                <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-2">
                  Why this matters
                </p>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {getWhyThisMatters(commitment)}
                </p>

                {/* Source evidence — Tufte: exhibit-like */}
                <div className="mt-4 pl-3 border-l-2" style={{ borderColor: '#2563EB' }}>
                  <p className="text-xs text-gray-400 mb-1">
                    {commitment.source.type} · {new Date(commitment.source.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </p>
                  <p className="text-sm italic text-gray-600 leading-relaxed">
                    "{commitment.source.snippet}"
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Actions — Tufte: minimal, clear, ordered by priority */}
        <div className="flex items-center gap-2 mt-5">
          <Button
            size={mode === 'dominant' ? 'default' : 'sm'}
            className="bg-gray-900 text-white hover:bg-gray-800"
          >
            {isOverdue ? 'Follow up now' : 'Mark as done'}
          </Button>
          {mode === 'dominant' && (
            <Button variant="ghost" size="default" className="text-gray-500">
              Snooze
            </Button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
            className="ml-auto flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            {expanded ? 'Less' : 'Details'}
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')}
            />
          </button>
        </div>
      </div>
      </motion.div>
    </ClickableCard>
  )
}

function getLayoutConfig(mode: LayoutMode) {
  switch (mode) {
    case 'dominant':
      return {
        padding: 'p-8',
        titleSize: 'text-2xl sm:text-3xl',
        entitySize: 'text-sm',
        urgencySize: 'text-sm',
      }
    case 'prominent':
      return {
        padding: 'p-6',
        titleSize: 'text-xl sm:text-2xl',
        entitySize: 'text-sm',
        urgencySize: 'text-sm',
      }
    case 'present':
      return {
        padding: 'p-5',
        titleSize: 'text-lg',
        entitySize: 'text-xs',
        urgencySize: 'text-xs',
      }
    case 'quiet':
      return {
        padding: 'p-4',
        titleSize: 'text-base',
        entitySize: 'text-xs',
        urgencySize: 'text-xs',
      }
    default:
      return {
        padding: 'p-4',
        titleSize: 'text-base',
        entitySize: 'text-xs',
        urgencySize: 'text-xs',
      }
  }
}

function getWhyThisMatters(c: Commitment): string {
  const due = new Date(c.dueDate)
  const hours = (due.getTime() - Date.now()) / 3600000
  if (hours < 0) {
    return `This commitment is overdue. ${c.entity} is waiting for you to deliver. ${c.isBlocking ? 'Other work depends on this being completed first.' : 'Delivering promptly will rebuild trust.'}`
  }
  if (hours < 4) {
    return `${c.entity} needs this within hours. ${c.isBlocking ? 'This is blocking other commitments and downstream work.' : 'Delivering on time maintains your reliability score.'}`
  }
  if (hours < 24) {
    return `Due today. ${c.entity} is expecting this by end of day. ${c.isBlocking ? 'Other commitments are waiting on this.' : ''}`
  }
  return `Part of your active commitments to ${c.entity}. ${c.isBlocking ? 'This is blocking other work.' : ''}`
}
