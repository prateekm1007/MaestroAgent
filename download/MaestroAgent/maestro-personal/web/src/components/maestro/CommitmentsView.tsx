'use client'

import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { CheckCircle2, Clock, AlertTriangle } from 'lucide-react'
import type { Commitment } from '@/lib/types'
import { calculateImportance, formatTimeUntil, getConfidenceStyle } from '@/lib/importance'
import { TheOne } from '@/components/maestro/TheOne'

interface CommitmentsViewProps {
  commitments: Commitment[]
}

export function CommitmentsView({ commitments }: CommitmentsViewProps) {
  if (commitments.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-lg text-gray-400">No active commitments.</p>
        <p className="text-sm text-gray-400 mt-1">
          Create a signal or connect a tool to start tracking promises.
        </p>
      </div>
    )
  }

  // Sort by importance score (highest first)
  const sorted = [...commitments].sort(
    (a, b) => calculateImportance(b) - calculateImportance(a),
  )

  // THE ONE = highest importance
  const theOne = sorted[0]
  const rest = sorted.slice(1)

  return (
    <div className="max-w-2xl mx-auto">
      {/* THE ONE — dominant */}
      <div className="mb-8">
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">
          The One
        </p>
        <TheOne commitment={theOne} />
      </div>

      {/* All Active — supporting */}
      {rest.length > 0 && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-3">
            All Active ({rest.length})
          </p>
          <div className="space-y-2">
            {rest.map((c, i) => (
              <CommitmentRow key={c.id} commitment={c} index={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function CommitmentRow({ commitment, index }: { commitment: Commitment; index: number }) {
  const confStyle = getConfidenceStyle(commitment.confidence)
  const timeStr = formatTimeUntil(commitment.dueDate)
  const isOverdue = new Date(commitment.dueDate).getTime() < Date.now()

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: index * 0.04, ease: [0.16, 1, 0.3, 1] }}
      className="flex items-center gap-3 py-3 px-4 bg-white rounded-lg border border-gray-100 hover:border-gray-200 transition-colors"
    >
      {/* Confidence dot — Bertin: color as value encoding */}
      <div
        className="h-2 w-2 rounded-full flex-shrink-0"
        style={{ background: confStyle.color }}
      />

      {/* Entity + text */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-700 truncate">{commitment.text}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {commitment.entity} · {commitment.source.type}
        </p>
      </div>

      {/* Due time */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {isOverdue ? (
          <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
        ) : (
          <Clock className="h-3.5 w-3.5 text-gray-300" />
        )}
        <span
          className={cn(
            'text-xs tabular-nums',
            isOverdue ? 'text-red-600 font-medium' : 'text-gray-400',
          )}
        >
          {timeStr}
        </span>
      </div>
    </motion.div>
  )
}
