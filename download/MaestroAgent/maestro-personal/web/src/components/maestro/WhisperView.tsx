'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { AlertTriangle, Calendar, Lightbulb, ChevronDown, X } from 'lucide-react'
import type { Whisper, WhisperType } from '@/lib/types'
import ClickableCard from './ClickableCard'

interface WhisperViewProps {
  whispers: Whisper[]
  apiBase?: string
  token?: string
}

export function WhisperView({ whispers, apiBase, token }: WhisperViewProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const visible = whispers.filter((w) => !dismissed.has(w.id))

  if (visible.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-lg text-gray-400">All caught up.</p>
        <p className="text-sm text-gray-400 mt-1">No proactive insights right now.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      {visible.map((whisper) => (
        <ClickableCard
          key={whisper.id}
          commitment={{
            commitment_id: whisper.id,
            entity: whisper.entity || whisper.title,
            text: whisper.context || whisper.title,
            state: 'active',
            confidence: whisper.probability ? whisper.probability / 100 : 0.5,
            source_signal_id: whisper.id,
          }}
          apiBase={apiBase || 'https://maestroagent-production.up.railway.app'}
          token={token || ''}
        >
          <WhisperCard
            whisper={whisper}
            expanded={expanded.has(whisper.id)}
            onToggle={() => {
              const next = new Set(expanded)
              if (next.has(whisper.id)) next.delete(whisper.id)
              else next.add(whisper.id)
              setExpanded(next)
            }}
            onDismiss={() => {
              const next = new Set(dismissed)
              next.add(whisper.id)
              setDismissed(next)
            }}
          />
        </ClickableCard>
      ))}
    </div>
  )
}

function WhisperCard({
  whisper,
  expanded,
  onToggle,
  onDismiss,
}: {
  whisper: Whisper
  expanded: boolean
  onToggle: () => void
  onDismiss: () => void
}) {
  const config = getWhisperConfig(whisper.type)

  return (
    <motion.div
      initial={config.initial}
      animate={config.animate}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: config.duration, ease: [0.16, 1, 0.3, 1] }}
      className={cn('relative w-full overflow-hidden ', config.bgClass, config.minHeight)}
    >
      <div className={cn('p-5', config.padding)}>
        {/* Header row */}
        <div className="flex items-start gap-3">
          <div className={cn('flex-shrink-0 mt-0.5', config.iconColor)}>
            {config.icon}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className={cn('font-semibold tracking-tight text-gray-900', config.titleSize)}>
              {whisper.title}
            </h3>
            {whisper.context && (
              <p className="text-sm text-gray-500 mt-1 leading-relaxed">
                {whisper.context}
              </p>
            )}
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onDismiss() }}
            className="flex-shrink-0 text-gray-300 hover:text-gray-500 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Probability — like weather: only show when grounded in facts */}
        {whisper.probability !== undefined && whisper.probabilityBasis && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-gray-500">Likelihood of slipping</span>
              <span className="text-sm font-medium  tabular-nums">
                {whisper.probability}%
              </span>
            </div>
            {/* Tufte: sparkline-style bar, thin */}
            <div className="h-1   overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${whisper.probability}%` }}
                transition={{ duration: 0.8, ease: 'easeOut', delay: 0.2 }}
                className="h-full "
                style={{ background: '#DC2626' }}
              />
            </div>
            {/* Factual basis — like weather forecast explanation */}
            <p className="text-xs text-gray-400 mt-2 leading-relaxed italic">
              {whisper.probabilityBasis}
            </p>
          </div>
        )}

        {/* Progressive disclosure: expanded content */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="overflow-hidden"
            >
              <div className="mt-4 pt-4 border-t border-gray-200/50">
                <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-2">
                  Why this matters
                </p>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {getWhisperReasoning(whisper)}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Actions */}
        {whisper.suggestedActions.length > 0 && (
          <div className="flex items-center gap-2 mt-4">
            {whisper.suggestedActions.map((action, i) => (
              <Button
                key={i}
                size="sm"
                variant={i === 0 ? 'default' : 'ghost'}
                onClick={(e) => e.stopPropagation()}
                className={cn(
                  i === 0 && config.actionClass,
                  i > 0 && 'text-gray-500',
                )}
              >
                {action.label}
              </Button>
            ))}
            <button
              onClick={(e) => { e.stopPropagation(); onToggle() }}
              className="ml-auto flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors"
            >
              {expanded ? 'Less' : 'Details'}
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

function getWhisperConfig(type: WhisperType) {
  switch (type) {
    case 'at_risk':
      return {
        bgClass: 'bg-gradient-to-b from-red-50 to-red-100/50',
        minHeight: 'min-h-[35vh]',
        padding: 'p-6',
        titleSize: 'text-lg',
        iconColor: '',
        icon: <AlertTriangle className="h-5 w-5" />,
        actionClass: 'bg-red-600 text-white hover:bg-red-700',
        initial: { opacity: 0, y: 30 },
        animate: { opacity: 1, y: 0 },
        duration: 0.3,
      }
    case 'preparation':
      return {
        bgClass: '/80',
        minHeight: 'min-h-[25vh]',
        padding: 'p-5',
        titleSize: 'text-base',
        iconColor: 'text-blue-500',
        icon: <Calendar className="h-5 w-5" />,
        actionClass: ' text-white hover:bg-blue-700',
        initial: { opacity: 0, x: 30 },
        animate: { opacity: 1, x: 0 },
        duration: 0.25,
      }
    case 'opportunity':
      return {
        bgClass: 'bg-green-50/80',
        minHeight: 'min-h-[18vh]',
        padding: 'p-5',
        titleSize: 'text-base',
        iconColor: 'text-green-500',
        icon: <Lightbulb className="h-5 w-5" />,
        actionClass: 'bg-green-600 text-white hover:bg-green-700',
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        duration: 0.2,
      }
    case 'quiet':
      return {
        bgClass: 'bg-transparent',
        minHeight: '',
        padding: 'py-2',
        titleSize: 'text-sm',
        iconColor: 'text-gray-300',
        icon: <Lightbulb className="h-4 w-4" />,
        actionClass: '',
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        duration: 0.15,
      }
  }
}

function getWhisperReasoning(w: Whisper): string {
  switch (w.type) {
    case 'at_risk':
      return `This commitment is at high risk of slipping. ${w.entity} hasn't responded in ${w.context?.match(/(\d+) days/)?.[1] || 'several'} days, which is significantly longer than their typical response time. Sending a follow-up now — before the deadline passes — gives you the best chance of keeping the commitment on track.`
    case 'preparation':
      return `You have a meeting with ${w.entity} soon. Reviewing the related commitments beforehand will help you address each one efficiently and demonstrate that you're tracking your obligations.`
    case 'opportunity':
      return `You've been consistently delivering for ${w.entity}. This is a natural moment to strengthen the relationship by asking for something in return — a referral, testimonial, or expanded scope.`
    case 'quiet':
      return w.context || 'An informational insight based on your commitment patterns.'
  }
}
