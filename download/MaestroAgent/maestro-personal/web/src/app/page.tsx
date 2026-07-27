'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Search, Calendar, Zap, Sun } from 'lucide-react'
import type { ViewTab, Commitment } from '@/lib/types'
import { calculateImportance, getLayoutMode } from '@/lib/importance'
import { mockCommitments, mockWhispers, mockChanges } from '@/lib/mockData'
import { TheOne } from '@/components/maestro/TheOne'
import { AskView } from '@/components/maestro/AskView'
import { WhisperView } from '@/components/maestro/WhisperView'
import { CommitmentsView } from '@/components/maestro/CommitmentsView'

export default function Home() {
  const [tab, setTab] = useState<ViewTab>('today')

  const sortedCommitments = [...mockCommitments].sort(
    (a, b) => calculateImportance(b) - calculateImportance(a),
  )
  const theOne = sortedCommitments[0]
  const rest = sortedCommitments.slice(1)

  return (
    <div className="min-h-screen bg-white flex flex-col">
      {/* Header — Tufte: minimal, no border, generous space */}
      <header className="sticky top-0 z-10 bg-white/95 backdrop-blur-sm">
        <div className="max-w-2xl mx-auto px-8 py-4 flex items-center justify-between">
          <span className="font-semibold text-sm tracking-tight text-gray-900">Maestro</span>
          <nav className="flex items-center gap-1">
            <NavButton active={tab === 'today'} onClick={() => setTab('today')} icon={<Sun className="h-3.5 w-3.5" />} label="Today" />
            <NavButton active={tab === 'ask'} onClick={() => setTab('ask')} icon={<Search className="h-3.5 w-3.5" />} label="Ask" />
            <NavButton active={tab === 'commitments'} onClick={() => setTab('commitments')} icon={<Calendar className="h-3.5 w-3.5" />} label="Commitments" />
            <NavButton active={tab === 'whisper'} onClick={() => setTab('whisper')} icon={<Zap className="h-3.5 w-3.5" />} label="Whisper" />
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-2xl w-full mx-auto px-8 py-10">
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
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Floating Ask — Tufte: minimal, functional */}
      {tab !== 'ask' && (
        <motion.button
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3, duration: 0.3 }}
          onClick={() => setTab('ask')}
          className="fixed bottom-6 right-6 z-20 flex items-center gap-2 px-4 py-2.5 bg-gray-900 text-white rounded-full shadow-lg hover:bg-gray-800 transition-colors"
        >
          <Search className="h-4 w-4" />
          <span className="text-sm font-medium">Ask</span>
        </motion.button>
      )}
    </div>
  )
}

function NavButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
        active
          ? 'bg-gray-100 text-gray-900 font-medium'
          : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50',
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  )
}

function TodayView({ theOne, rest }: { theOne: Commitment; rest: Commitment[] }) {
  const score = calculateImportance(theOne)
  const mode = getLayoutMode(score)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="space-y-10">
      {/* Greeting — Tufte: direct, personal, no card */}
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">
          {greeting}.
        </h1>
        {mode === 'dominant' || mode === 'prominent' ? (
          <p className="text-gray-400 mt-2 text-base">
            You have {mode === 'dominant' ? 'one promise' : 'a few promises'} that need attention.
          </p>
        ) : mode === 'empty' ? (
          <p className="text-gray-400 mt-2 text-base">
            You&rsquo;re clear today. No commitments need attention.
          </p>
        ) : (
          <p className="text-gray-400 mt-2 text-base">
            Here&rsquo;s what needs your attention.
          </p>
        )}
      </div>

      {/* THE ONE — adaptive emphasis */}
      <TheOne commitment={theOne} />

      {/* What Changed — SINGLE section, shows actual changes not commitment list */}
      <div className={cn(mode === 'dominant' && 'opacity-60')}>
        <p className="text-xs font-medium uppercase tracking-wider text-gray-400 mb-4">
          What Changed
        </p>
        <div className="space-y-3">
          {mockChanges.map((change, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.25 }}
              className="flex items-start gap-3"
            >
              {/* Change type indicator — Bertin: color = meaning */}
              <div className={cn(
                'flex-shrink-0 mt-1 h-1.5 w-1.5 rounded-full',
                change.type === 'new' && 'bg-blue-400',
                change.type === 'transition' && 'bg-amber-400',
                change.type === 'deadline' && 'bg-red-400',
                change.type === 'completion' && 'bg-green-400',
              )} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 leading-relaxed">
                  {change.text}
                </p>
                <p className="text-xs text-gray-400 mt-0.5 tabular-nums">
                  {change.entity} · {change.timeAgo}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
